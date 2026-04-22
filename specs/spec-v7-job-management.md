---
version: 7
name: job-management
display_name: "Job Management"
status: complete
created: 2026-03-28
depends_on: [5]
tags: [frontend, api, ui]
---

# Job Management

## Why (Problem Statement)

> As a user, I want to see what jobs are currently running, cancel a running job if needed, and re-queue a failed job so that I have visibility and control over my generation pipeline.

### Context

- Currently the UI shows one job at a time in the main panel — if you navigate away or submit again, the previous job's state is lost
- There is no way to cancel a job that's been submitted but hasn't completed
- Failed jobs can only be retried by re-typing the prompt; no "retry" shortcut exists
- The DynamoDB table and `GET /jobs` (if exposed) can return all jobs; the API has a `GET /jobs/{id}` endpoint but no list endpoint yet
- The job history panel shows completed/failed jobs from localStorage, but does not reflect live server state

---

## What (Requirements)

### User Stories

- **US-1**: As a user, I want to see a live indicator of all in-flight jobs so I know what's generating
- **US-2**: As a user, I want to cancel a running or pending job so I can stop a bad prompt without waiting
- **US-3**: As a user, I want to click "Retry" on a failed job in history so I can resubmit with the same params in one click
- **US-4**: As a user, I want to see a job's error message when it fails so I understand what went wrong

### Acceptance Criteria

- AC-1: A `GET /jobs` API endpoint returns jobs filtered by status (optional `?status=RUNNING`)
- AC-2: The UI polls for running jobs and shows them as an "active" list (distinct from completed history)
- AC-3: Each running job has a Cancel button that calls `DELETE /jobs/{id}` or `POST /jobs/{id}/cancel`
- AC-4: Each failed job in history has a Retry button that re-submits with the same params
- AC-5: Cancelling a job updates its status in the UI immediately (optimistic update)
- AC-6: Failed job entries show the error message on hover or expand

### Out of Scope

- Pagination of job list (cap at 20 most recent)
- Job priority / reordering
- Multi-select cancel

---

## How (Approach)

### Phase 1: API — List and Cancel Endpoints

- Add `GET /jobs` endpoint to `routers/jobs.py` — queries DynamoDB GSI by status+created_at, returns list of jobs (limit 20, optional `?status=` filter)
- Add `POST /jobs/{id}/cancel` endpoint — updates DynamoDB status to `CANCELLED`, attempts to interrupt ComfyUI via `POST /interrupt` if job is RUNNING
- Add `dynamo.list_jobs(status, limit)` to `services/dynamo.py`
- Write integration tests for both endpoints against LocalStack

### Phase 2: Frontend — Active Jobs Hook

- Add `hooks/useActiveJobs.ts` — polls `GET /jobs?status=RUNNING` every 3s, returns list of active jobs + `cancelJob(id)` action
- `cancelJob` calls `POST /jobs/{id}/cancel`, optimistically removes the job from the active list

### Phase 3: Frontend — Active Jobs UI

- Add an "Active" section above the History panel in the right sidebar (only shown when jobs are in-flight)
- Each entry shows: status badge, truncated prompt, elapsed time, Cancel button
- On cancel: entry fades out immediately (optimistic), re-appears with CANCELLED status if the cancel fails

### Phase 4: Frontend — Retry on Failed Jobs

- Add a Retry button to failed `HistoryEntry` rows in `JobHistory.tsx`
- Clicking Retry calls the existing `submit()` from `useJob` with `entry.params`
- Wire `submit` down from `App.tsx` as an `onRetry` prop on `JobHistory`

### Phase 5: Tests

- Integration test: `GET /jobs` returns correct list, filters by status
- Integration test: `POST /jobs/{id}/cancel` transitions status to CANCELLED
- Frontend: Vitest + RTL — active jobs list renders, cancel button triggers optimistic removal

---

## Technical Notes

### Architecture Decisions

- `POST /jobs/{id}/cancel` preferred over `DELETE` — semantically cancellation is a state transition, not a deletion; the job record is preserved for history
- ComfyUI `/interrupt` only stops the currently executing prompt; if the job is PENDING (queued but not running), only the DynamoDB status update is needed
- Polling interval 3s for active jobs — short enough to feel live, long enough to avoid hammering the API
- Cap list at 20 — the DynamoDB GSI is already sorted by `created_at`; take the 20 most recent

### Dependencies

- DynamoDB GSI on `status` + `created_at` — already exists per `storage.ts`
- ComfyUI `/interrupt` endpoint — available in ComfyUI HTTP API

### Risks & Mitigations

| Risk                                                    | Mitigation                                                        |
| ------------------------------------------------------- | ----------------------------------------------------------------- |
| Interrupt races: ComfyUI finishes before cancel arrives | Status check after interrupt; if already COMPLETED, leave as-is   |
| Multiple users: cancel affects shared ComfyUI queue     | Single-user deployment assumption; revisit if multi-tenant needed |
| GSI eventually consistent                               | Acceptable for a polling UI — stale by at most one poll cycle     |

---

## Open Questions

~~1. Should cancelled jobs appear in the history sidebar, or be hidden?~~
**Resolved**: Cancelled jobs show in history with CANCELLED status badge. Users can manually delete individual history entries if desired — add a per-entry delete button to `JobHistory`.

~~2. Should Retry generate a new seed or reuse the exact seed from the original job?~~
**Resolved**: Retry uses the exact seed for exact reproduction. The user can then modify seed/params in the form before re-submitting.

---

## Changelog

| Date       | Change        |
| ---------- | ------------- |
| 2026-03-28 | Initial draft |
