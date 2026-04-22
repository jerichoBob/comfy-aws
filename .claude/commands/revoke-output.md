# Revoke Job Output

Revoke all generated images for a job: delete from S3 and invalidate CloudFront cache.

## Usage

```
/revoke-output <job_id> [--profile <aws_profile>]
```

## What it does

1. Deletes all S3 objects at `s3://{S3_BUCKET}/outputs/{job_id}/`
2. Creates a CloudFront invalidation for `/outputs/{job_id}/*`
3. Reports the invalidation ID (URL access blocked within ~60 seconds)

## Prerequisites

Set these environment variables before running:

```bash
export S3_BUCKET=<your-bucket-name>
export CLOUDFRONT_DISTRIBUTION_ID=<your-distribution-id>
```

Find the distribution ID:

```bash
aws cloudfront list-distributions \
  --query 'DistributionList.Items[*].[Id,DomainName]' \
  --output table --profile personal
```

## Instructions

Run the revocation script:

```bash
bash .claude/scripts/revoke-output.sh $ARGUMENTS
```

Where `$ARGUMENTS` is the job_id and any optional flags passed to this command.

Report the result including the CloudFront invalidation ID.
