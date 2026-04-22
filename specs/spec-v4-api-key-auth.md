---
version: 4
name: api-key-auth
display_name: "API Key Authentication"
status: complete
created: 2026-03-27
depends_on: [1]
tags: [security, fastapi, middleware, auth]
---

# API Key Authentication

## Why (Problem Statement)

> As an operator, I want all API endpoints protected by a shared secret so that only authorized clients can submit jobs or query results, while keeping local development frictionless.

### Context

- The API currently has no authentication — anyone who can reach the ALB can submit jobs and rack up GPU charges
- ALB health checks and monitoring probes must reach `GET /health` without credentials; a blanket auth layer would break these
- Local dev should work out of the box with zero config (empty `API_KEYS` disables auth entirely)
- A simple shared-key scheme is sufficient at this scale; OAuth/JWT would add infra complexity with no benefit for a single-tenant internal API
- Key prefixes logged per request provide an audit trail without storing the full secret in logs

---

## What (Requirements)

### User Stories

- **US-1**: As an API client, I want to include `X-API-Key: <key>` in my requests so that I can access protected endpoints
- **US-2**: As an operator, I want to rotate or add keys by changing an env var (no redeploy of code required, only task restart)
- **US-3**: As a developer, I want `docker compose up` to work with no auth config so I'm not blocked during local dev
- **US-4**: As a monitoring system (ALB, uptime checks), I want `GET /health` to always return 200 without credentials

### Acceptance Criteria

- AC-1: A request to any endpoint other than `GET /health` without `X-API-Key` returns `401 {"detail": "Invalid or missing API key"}`
- AC-2: A request with a valid key in `API_KEYS` returns the normal response
- AC-3: A request with an invalid key returns `401 {"detail": "Invalid or missing API key"}`
- AC-4: `GET /health` returns `200` with no `X-API-Key` header, regardless of `API_KEYS` value
- AC-5: When `API_KEYS=""` (default), all requests pass through unauthenticated — no false 401s
- AC-6: Each authenticated request logs `key_prefix=<first 8 chars>` at INFO level for audit
- AC-7: Multiple keys (comma-separated in `API_KEYS`) are all accepted independently

### Out of Scope

- Per-key rate limiting or scoping — all valid keys have equal access
- Key rotation without restart — changing `API_KEYS` requires an ECS task restart (acceptable)
- JWT or OAuth — not needed at this scale
- Protecting `GET /health` — explicitly excluded

---

## How (Approach)

### Phase 1: Middleware Implementation

**Task 1.1 — Config: add `API_KEYS` to `config.py`**

- Add `api_keys: str = ""` to `Settings`
- Add helper property `api_key_set: set[str]` that splits on `,`, strips whitespace, and filters empty strings
- Auth is disabled when `api_key_set` is empty

**Task 1.2 — Middleware: implement `ApiKeyMiddleware` in `api/app/middleware/auth.py`**

- Starlette `BaseHTTPMiddleware` subclass
- Skip auth (call next) if:
  - `settings.api_key_set` is empty, OR
  - `request.url.path == "/health"` and `request.method == "GET"`
- Extract `X-API-Key` header; if missing or not in `api_key_set`, return `JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)`
- On success, log `INFO auth key_prefix=%s`, `key[:8]`

**Task 1.3 — Wire middleware into `main.py`**

- `app.add_middleware(ApiKeyMiddleware)` after app creation, before router inclusion

**Task 1.4 — Unit tests: `api/tests/test_auth_middleware.py`**

- Use FastAPI `TestClient` with a minimal test app (no mocks — real middleware, real settings override via env)
- Test: no key, auth enabled → 401
- Test: wrong key, auth enabled → 401
- Test: valid key, auth enabled → 200
- Test: no key, auth disabled (`API_KEYS=""`) → 200
- Test: `GET /health` with auth enabled and no key → 200
- Test: multiple keys, each accepted independently

**Task 1.5 — Integration test: auth behavior against running stack**

- Add `test_auth` cases to `api/tests/test_integration.py`
- `POST /jobs` without key (when `API_KEYS` set in env) → 401
- `POST /jobs` with valid key → not 401 (job created or 422 from missing body — not an auth failure)
- `GET /health` without key → 200 always

### Phase 2: Docker + Deployment Wiring

**Task 2.1 — `docker-compose.yml`: add `API_KEYS` env var (empty default)**

- Under `api` service `environment:`, add `API_KEYS: ""` with a comment noting auth is disabled in local dev

**Task 2.2 — ECS task definition: pass `API_KEYS` from SSM or env**

- In `infra/lib/constructs/service.ts`, add `API_KEYS` to the `api` container environment
- Source from SSM Parameter Store at `/comfy-aws/api-keys` (operator sets this before deploy)
- Document the SSM path in the deployment runbook

**Task 2.3 — Update `CLAUDE.md` environment variable table**

- Add `API_KEYS` row: default `""`, description "Comma-separated valid API keys; empty disables auth"

---

## Technical Notes

### Architecture Decisions

- **Middleware over dependency injection**: A FastAPI dependency on every router would require touching each route and could be accidentally omitted on new routes. A Starlette `BaseHTTPMiddleware` is applied globally — new routes are protected automatically.
- **`/health` exempted by path, not by router**: The health router is defined in `app/routers/health.py` and has no awareness of auth. The exemption lives entirely in the middleware, making it easy to audit in one place.
- **`API_KEYS` as comma-separated string, not JSON list**: Matches the convention of other env vars in the project (simple strings). Easy to set in ECS task definition console, SSM, or shell without quoting issues.
- **First 8 chars as key prefix**: Long enough to distinguish keys in logs, short enough that a log scraper can't reconstruct a useful fragment. Standard practice (similar to GitHub personal access token prefix display).
- **Auth disabled when `API_KEYS` is empty**: Eliminates the need for a separate `AUTH_ENABLED` toggle. Empty string is the natural "not configured" state and is the correct local dev default.

### Key File Paths

| File                                | Change                                           |
| ----------------------------------- | ------------------------------------------------ |
| `api/app/config.py`                 | Add `api_keys: str = ""`, `api_key_set` property |
| `api/app/middleware/__init__.py`    | New package                                      |
| `api/app/middleware/auth.py`        | New: `ApiKeyMiddleware` implementation           |
| `api/app/main.py`                   | `app.add_middleware(ApiKeyMiddleware)`           |
| `api/tests/test_auth_middleware.py` | New: unit tests for middleware                   |
| `api/tests/test_integration.py`     | Add auth integration test cases                  |
| `docker-compose.yml`                | Add `API_KEYS: ""` to `api` service env          |
| `infra/lib/constructs/service.ts`   | Pass `API_KEYS` from SSM to `api` container      |

### Dependencies

- `starlette` (already installed via `fastapi`)
- No new Python packages required

### Risks & Mitigations

| Risk                                             | Mitigation                                                                 |
| ------------------------------------------------ | -------------------------------------------------------------------------- |
| New route added without realizing it's protected | Middleware is global — protection is automatic; document this in CLAUDE.md |
| `API_KEYS` accidentally committed to git         | Set via SSM in AWS, via `.env` (gitignored) locally; never hardcoded       |
| ALB health check blocked by auth                 | `/health` is unconditionally exempt in middleware                          |
| Key leaked in logs if prefix is too long         | 8-char prefix is short enough to be non-exploitable                        |
| Middleware performance overhead                  | Header lookup is O(1) set membership; negligible at any realistic RPS      |

---

## Changelog

| Date       | Change        |
| ---------- | ------------- |
| 2026-03-27 | Initial draft |
