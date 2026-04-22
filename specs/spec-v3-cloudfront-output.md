---
version: 3
name: cloudfront-output
display_name: "CloudFront Output Delivery"
status: complete
created: 2026-03-27
depends_on: [1]
tags: [aws, cloudfront, s3, cdn, security, cdk]
---

# CloudFront Output Delivery

## Why (Problem Statement)

> As an API consumer, I want generated image URLs that don't expire and can be revoked, so that I can store job results long-term without managing URL refresh logic.

### Context

The current design stores S3 presigned URLs in DynamoDB at upload time. These have three compounding problems:

1. **Expiry**: Presigned URLs expire after 1 hour. A client who reads `GET /jobs/{id}` more than an hour after completion gets a dead link — even though the image is still in S3 and the job record is valid for 7 days.
2. **Irrevocability**: Presigned URLs are HMAC-signed bearer tokens tied to IAM credentials. They cannot be revoked before expiry without rotating the signing key, which breaks all outstanding URLs simultaneously. GDPR "right to erasure" is therefore unimplementable cleanly.
3. **Direct S3 exposure**: The bucket is currently private, but the presigned URL approach means the S3 bucket name and key structure are visible in every URL — unnecessary attack surface.

CloudFront + Origin Access Control (OAC) solves all three:

- Signed CloudFront URLs can have any expiry, can be invalidated per-path
- The S3 bucket is completely locked — no direct access possible, not even with valid AWS credentials
- URL generation happens at request time (`GET /jobs/{id}`), so the URL in the response is always fresh

---

## What (Requirements)

### User Stories

- **US-1**: As an API consumer, I want image URLs in `GET /jobs/{id}` to always be valid so I don't need to re-fetch before downloading
- **US-2**: As an operator, I want to be able to delete a user's images and revoke their URL access immediately so I can comply with deletion requests
- **US-3**: As a developer, I want the local dev environment to continue working unchanged so I don't need CloudFront running locally

### Acceptance Criteria

- AC-1: `GET /jobs/{id}` for a COMPLETED job returns CloudFront signed URLs valid for the remainder of the job's 7-day DynamoDB TTL
- AC-2: After `aws s3 rm s3://{bucket}/outputs/{job_id}/ --recursive` + CloudFront invalidation, the URL returns 403/404 within 60 seconds
- AC-3: Direct S3 `GET` to the output key (with valid AWS credentials) returns 403 — bucket denies all direct access
- AC-4: `docker compose up` local dev continues to use LocalStack S3 presigned URLs — no CloudFront dependency in local dev
- AC-5: `cdk synth` produces no errors; CloudFront distribution, OAC, and key group are all defined

### Out of Scope

- Public (unsigned) CloudFront URLs — all output URLs remain access-controlled
- CloudFront for model assets (`models/` prefix) — models are operator-managed, not user-facing
- CloudFront WAF rules — separate hardening concern
- Streaming / range requests for video output — not relevant yet

---

## How (Approach)

### Phase 1: CDK — CloudFront Distribution

- Add `CdnConstruct` in `infra/lib/constructs/cdn.ts`
- Create CloudFront Origin Access Control (OAC) for S3 (use `aws_cloudfront.S3OriginAccessControl`)
- Create CloudFront distribution with:
  - S3 bucket as origin using OAC
  - Default cache behavior: `outputs/*` prefix, signed URLs required, HTTPS only, `PriceClass.PRICE_CLASS_100` (US/Europe/Asia)
  - Viewer protocol policy: redirect HTTP → HTTPS
- Add bucket policy statement: deny all `s3:GetObject` on `outputs/*` except from CloudFront OAC principal
- Generate RSA-2048 key pair for CloudFront signed URLs (use `aws_cloudfront.PublicKey` + `KeyGroup`)
- Store private key PEM in SSM Parameter Store (standard tier, no cost) at path `/comfy-aws/cloudfront-private-key`
- Grant ECS task IAM role `ssm:GetParameter` on that path
- Export: CloudFront domain name, key pair ID as CDK stack outputs

### Phase 2: API — Key Loading & URL Generation

- Add to `config.py`:
  - `cloudfront_domain: str = ""` — empty = local dev, falls back to S3 presigned
  - `cloudfront_key_pair_id: str = ""`
  - `cloudfront_private_key_ssm_path: str = "/comfy-aws/cloudfront-private-key"`
- Add `services/cdn.py`:
  - On startup: if `cloudfront_domain` is set, fetch private key PEM from SSM, cache in memory
  - `generate_signed_url(s3_key: str, expires_in_seconds: int) -> str` using `cryptography` library (RSA SHA-1 HMAC per CloudFront spec)
- Feature flag pattern in `services/s3.py`: `upload_image()` returns `(s3_key, presigned_url)` tuple; presigned URL used only when CloudFront not configured

### Phase 3: API — Store Keys, Generate URLs at Request Time

- Update `services/dynamo.py`: store `output_keys: list[str]` (S3 keys) instead of `output_urls` — keys never expire
- Update `models/job.py`: remove `output_urls` from the stored model; add it as a computed field populated at read time
- Update `routers/jobs.py` `GET /jobs/{id}`: after fetching job from DynamoDB, call `cdn.generate_signed_url()` (or `s3.generate_presigned_url()` in local dev) for each key in `output_keys`; attach to response
- Expiry calculation: `min(job.expires_at - now, 7 days)` — URL expires when the job record does
- Write unit tests for `cdn.generate_signed_url()` using a fixed test key pair (no AWS calls needed — pure crypto)

### Phase 4: Revocation Helper Script

- Add `.claude/scripts/revoke-output.sh {job_id}`:
  - `aws s3 rm s3://{bucket}/outputs/{job_id}/ --recursive`
  - `aws cloudfront create-invalidation --distribution-id {dist_id} --paths "/outputs/{job_id}/*"`
  - Prints confirmation with invalidation ID
- Add corresponding `.claude/commands/revoke-output.md` slash command

---

## Technical Notes

### Architecture Decisions

- **OAC over OAI**: AWS deprecated Origin Access Identity (OAI) in favor of Origin Access Control (OAC) in 2022. OAC supports more S3 features (SSE-KMS, cross-account) and is the current recommendation. Use `S3OriginAccessControl` CDK L2 construct.
- **URL generation at request time, not upload time**: Decouples the image lifecycle from the URL lifecycle. S3 keys are permanent identifiers; signed URLs are ephemeral views. This is the correct separation.
- **SSM Parameter Store over Secrets Manager**: The CloudFront private key is a deployment secret (not a runtime rotating credential). SSM standard tier costs $0/month vs Secrets Manager's $0.40/secret/month. For a single key, SSM is the right call.
- **`cryptography` library over `boto3` for URL signing**: CloudFront signed URLs are generated locally using RSA + SHA-1. No AWS API call at request time — zero latency, zero cost per URL.
- **`PriceClass.PRICE_CLASS_100`**: Covers US, Canada, Europe, Israel. Excludes South America, Africa, Asia-Pacific. Reduces CloudFront cost ~40% vs `ALL`. Change to `ALL` if latency to Asia matters.
- **Local dev unchanged**: `CLOUDFRONT_DOMAIN` unset → falls back to S3 presigned URLs via LocalStack. No mocking, no conditional test paths.

### Cost Analysis

#### Dormant cost (no traffic)

| Resource                       | Cost                    |
| ------------------------------ | ----------------------- |
| CloudFront distribution        | $0 (no standing charge) |
| SSM Parameter Store (standard) | $0                      |
| S3 bucket (already exists)     | $0                      |
| **Total new dormant cost**     | **$0/month**            |

#### Active cost (per image delivered)

| Item                         | Rate         | Notes                            |
| ---------------------------- | ------------ | -------------------------------- |
| CloudFront HTTPS requests    | $0.009 / 10k | 1,000 image fetches = $0.0009    |
| CloudFront data transfer     | $0.009 / GB  | 1MB image × 1,000 = 1GB = $0.009 |
| S3 → CloudFront transfer     | $0           | Same-region, no egress charge    |
| S3 → client direct (current) | $0.09 / GB   | CloudFront is 10× cheaper        |

CloudFront is **cheaper than direct S3 delivery** for data transfer, and effectively free at personal scale.

#### Comparison to current approach

|                | Current (S3 presigned) | v3 (CloudFront)           |
| -------------- | ---------------------- | ------------------------- |
| Dormant cost   | $0                     | $0                        |
| Data transfer  | $0.09/GB               | $0.009/GB                 |
| URL revocation | ❌ impossible          | ✅ per-path invalidation  |
| URL expiry     | 1 hour (broken UX)     | 7 days (matches job TTL)  |
| Bucket exposed | Bucket name in URL     | ❌ CloudFront domain only |

### Dependencies

- AWS CloudFront (CDK L2: `aws_cloudfront`, `aws_cloudfront_origins`)
- AWS SSM Parameter Store (standard tier)
- Python `cryptography` library (RSA signing for CloudFront URLs)
- Existing S3 bucket and IAM task role from `StorageConstruct` and `ServiceConstruct`

### Key File Paths

- `infra/lib/constructs/cdn.ts` — new CloudFront construct
- `infra/lib/comfy-aws-stack.ts` — wire CdnConstruct, pass domain/key outputs to ServiceConstruct
- `api/app/services/cdn.py` — new: SSM key fetch, signed URL generation
- `api/app/services/s3.py` — returns S3 key alongside upload; presigned URL only for local dev
- `api/app/services/dynamo.py` — store `output_keys` instead of `output_urls`
- `api/app/models/job.py` — `output_urls` becomes computed at read time
- `api/app/routers/jobs.py` — generate URLs when building response
- `api/app/config.py` — add CloudFront env vars
- `.claude/scripts/revoke-output.sh` — operator revocation helper

### Risks & Mitigations

| Risk                                                                   | Mitigation                                                                                                                          |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| CloudFront propagation delay (~15 min on deploy)                       | One-time cost on CDK deploy; no impact on normal operation                                                                          |
| Private key rotation invalidates all outstanding URLs                  | Rotation is manual/infrequent; document rotation runbook; URLs are short-lived anyway                                               |
| `cryptography` library RSA signing uses SHA-1 (CloudFront requirement) | SHA-1 is required by CloudFront's signed URL spec — not a weakness here (it's not used for data integrity, only URL authentication) |
| SSM GetParameter adds latency on cold start                            | Key is fetched once at startup and cached in memory; no per-request SSM call                                                        |
| Local dev missing CloudFront                                           | Feature flag: `CLOUDFRONT_DOMAIN` unset → S3 presigned. Tests that need CloudFront behavior can use a real key pair locally         |
