---
version: 9
name: bearer-auth
display_name: "Bearer Token Auth"
status: pending
created: 2026-04-21
depends_on: [4]
tags: [api, security]
---

# Bearer Token Auth

## Why (Problem Statement)

> The API needs to be reachable from a browser or CLI running on a machine that is not the ECS host. The current `X-API-Key` header works fine for server-to-server calls but is non-standard and rejected by default CORS preflight policies. Adding `Authorization: Bearer <token>` support makes the API compatible with standard HTTP clients (`fetch`, `curl -u`, OpenAPI tooling) and paves the way for the remote frontend and CLI client in v10.

### Context

- Existing auth: `ApiKeyMiddleware` checks `X-API-Key` header; enabled when `API_KEYS` env var is non-empty
- The shared secret IS the token — no JWT, no OAuth server, no expiry. A static pre-shared key is appropriate for a single-operator deployment
- `X-API-Key` support must be retained for backward compatibility with any existing tooling
- The middleware currently lives in `api/app/middleware/auth.py` and is fully unit-tested

---

## What (Requirements)

### User Stories

- **US-1**: As a developer, I want to call the API with `curl -H "Authorization: Bearer <key>"` using the standard header so I don't need to remember a custom header name
- **US-2**: As a frontend developer, I want to use the standard `Authorization` header so the browser's Fetch API handles CORS preflight correctly
- **US-3**: As an operator, I want both `X-API-Key` and `Authorization: Bearer` to be accepted so existing integrations don't break

### Acceptance Criteria

- **AC-1**: A request with `Authorization: Bearer <valid-key>` is accepted (200) when auth is enabled
- **AC-2**: A request with `X-API-Key: <valid-key>` continues to be accepted — no regression
- **AC-3**: A request with `Authorization: Bearer <invalid-key>` is rejected (401)
- **AC-4**: A request with a well-formed `Authorization` header but wrong scheme (e.g. `Basic ...`) is rejected (401), not passed through
- **AC-5**: `GET /health` remains exempt from auth regardless of header
- **AC-6**: When `API_KEYS=""` (auth disabled), both header forms are ignored and all requests pass
- **AC-7**: The `useApi.ts` hook sends `Authorization: Bearer <key>` instead of `X-API-Key: <key>`
- **AC-8**: All existing `test_auth_middleware.py` tests still pass; new tests cover the Bearer cases

---

## How (Approach)

### Phase 1: Middleware Update

Update `ApiKeyMiddleware` in `api/app/middleware/auth.py`:

```python
def _extract_key(self, request: Request) -> str | None:
    # 1. Check Authorization: Bearer <token>
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    # 2. Fall back to X-API-Key (backward compat)
    return request.headers.get("x-api-key") or None
```

- Replace the current single-header check with `_extract_key()`
- Logic otherwise unchanged: extracted key checked against `settings.api_key_set`
- Reject 401 if `Authorization` header is present but scheme is not `Bearer` and `X-API-Key` is also absent — prevents silent pass-through of malformed auth

### Phase 2: Frontend Update

In `hooks/useApi.ts`, update `apiFetch()`:

```ts
// Before:
headers["X-API-Key"] = apiKey;
// After:
headers["Authorization"] = `Bearer ${apiKey}`;
```

- No change to key storage (localStorage key stays the same)
- No change to `ApiKeyInput.tsx` or the settings UI

### Phase 3: Tests

Add to `api/tests/test_auth_middleware.py`:

- `test_bearer_valid_key` — `Authorization: Bearer <key>` → 200
- `test_bearer_invalid_key` — `Authorization: Bearer wrong` → 401
- `test_bearer_wrong_scheme` — `Authorization: Basic <key>` → 401
- `test_x_api_key_still_works` — existing header → 200 (regression)
- `test_bearer_disabled_auth` — `Authorization: Bearer anything` with `API_KEYS=""` → 200

---

## Technical Notes

- No token expiry, rotation, or revocation in this spec — that's a future concern if the deployment becomes multi-user
- The key is a shared secret stored in SSM (`/comfy-aws/api-keys`); rotation requires an SSM update + task restart
- `Authorization` is a CORS-safelisted header in modern browsers; no CORS preflight is triggered for simple requests. The CORS configuration in v10 will explicitly allow `Authorization` in `allow_headers` for non-simple requests

---

## Changelog

| Date | Change |
|------|--------|
| 2026-04-21 | Initial draft |
