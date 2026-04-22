---
version: 5
name: react-ui
display_name: "React Generation UI"
status: complete
created: 2026-03-27
depends_on: [1, 4]
tags: [frontend, react, typescript, vite, ui]
---

# React Generation UI

## Why (Problem Statement)

> As a user, I want a polished browser interface for submitting image generation jobs and browsing my results so that I don't need to construct curl commands or read raw JSON.

### Context

- The API is fully functional but requires clients to construct typed JSON payloads, know workflow IDs, and poll for completion manually — not practical for daily use
- ComfyUI's native UI is powerful but exposes the raw node graph, which is hostile to non-technical users and not appropriate for production
- A thin React app sitting in front of the existing API can provide a production-grade generation UI with zero changes to the backend
- The frontend is deployed as static files served by FastAPI at `/ui` — same container, no extra infrastructure; for local dev it runs on port 5173 with a `/api` proxy to avoid CORS

---

## What (Requirements)

### User Stories

- **US-1**: As a user, I want to select a checkpoint, workflow, sampler, and scheduler from dropdowns populated by live API data so I'm never working with stale lists
- **US-2**: As a user, I want to write positive and negative prompts in large, clearly labeled text areas so I can focus on creative intent without hunting for inputs
- **US-3**: As a user, I want steps, CFG, seed, width, and height controls with sensible defaults and a "randomize seed" button so I can tune parameters without trial-and-error
- **US-4**: As a user, I want to submit a job and see a loading state while it runs, then see the generated image with metadata (duration, seed, model) and a download button
- **US-5**: As a user, I want to scroll through recent jobs with thumbnails and status badges so I can revisit previous generations
- **US-6**: As an operator, I want to enter an API key that persists across sessions so authenticated deployments work from the browser
- **US-7**: As a developer, I want a connection status indicator so I immediately see if the API is unreachable without reading a network error

### Acceptance Criteria

- AC-1: Checkpoint, LoRA, and VAE dropdowns are populated from `GET /models` on load; no hardcoded values
- AC-2: Workflow selector lists all workflow IDs from `GET /workflows`; selecting one updates the visible schema fields
- AC-3: Submitting the form calls `POST /jobs`, then polls `GET /jobs/{id}` every 2s until `COMPLETED` or `FAILED`; a spinner is shown during polling
- AC-4: On `COMPLETED`, the generated image renders inline; metadata row shows duration (seconds), seed used, and checkpoint name; a download link is present
- AC-5: On `FAILED`, the error message from the API is displayed clearly with a retry affordance
- AC-6: Job history panel shows the last 20 jobs (from localStorage + in-flight state) with thumbnail, status badge, and elapsed time; clicking a job restores its result view
- AC-7: Connection status indicator polls `GET /health` every 10s; shows green/red dot with "Connected" / "Unreachable" label
- AC-8: API key field in a settings panel persists to `localStorage`; value is sent as `X-Api-Key` header on every request
- AC-9: `npm run dev` starts on port 5173; `/api/*` proxies to `http://localhost:8000`
- AC-10: `npm run build` produces a `dist/` directory; FastAPI serves it at `/ui` with `StaticFiles`; `GET /ui` redirects to `GET /ui/index.html`
- AC-11: Layout is usable at 1280px wide and degrades gracefully to a single-column view at 768px

### Out of Scope

- Real-time WebSocket progress bars (streaming generation events) — future spec
- Authentication flows (OAuth, Cognito) — API key header is sufficient for v5
- Image upload for img2img workflows — future spec
- Multi-user session management — single-user browser context

---

## How (Approach)

### Phase 1: Project Scaffold

- Initialize `frontend/` with Vite: `npm create vite@latest frontend -- --template react-ts`
- Add dependencies: `tailwindcss`, `@tailwindcss/vite`, `lucide-react`, `clsx`
- Configure Tailwind: extend theme with Inter font (`fontFamily.sans`), add a neutral dark surface palette (`zinc-900`, `zinc-800`, `zinc-700`) for the app chrome
- Add `vite.config.ts` proxy: `server.proxy['/api'] = { target: 'http://localhost:8000', rewrite: path => path.replace(/^\/api/, '') }`
- Add `frontend/` to `.gitignore` patterns for `node_modules/` and `dist/`
- Validate: `npm run dev` opens a blank page at `localhost:5173`; `npm run build` exits 0

### Phase 2: Core UI Components

- `components/Sidebar.tsx` — fixed left column (256px): checkpoint dropdown, workflow selector, sampler dropdown, scheduler dropdown; each labeled and sourced from API context; skeleton loaders while fetching
- `components/PromptForm.tsx` — main content area: "Positive prompt" `<textarea>` (4 rows, full width), "Negative prompt" `<textarea>` (2 rows); both resizable vertically; character count in corner
- `components/SettingsPanel.tsx` — below prompts: steps slider (1–150, default 20), CFG slider (1–20, step 0.5, default 7), seed number input + randomize button (Shuffle icon, generates random int), width/height selects (512/768/1024/1280, default 1024×1024)
- `components/SubmitButton.tsx` — full-width primary button; idle: "Generate"; loading: spinner + "Generating…"; disabled during in-flight job
- All components styled with Tailwind utility classes only; no CSS files; component props fully typed

### Phase 3: API Integration

- `hooks/useApi.ts` — central hook: loads models + workflows on mount, exposes `{ models, workflows, loading, error }`; reads `X-Api-Key` from localStorage; all fetch calls go through a shared `apiFetch(path, init?)` wrapper that injects the header and prefixes `/api`
- `hooks/useJob.ts` — manages job submission and polling: `submit(params) → void`; internal state machine `idle → submitting → polling → done | failed`; polls every 2s with `setInterval`, clears on `done`/`failed`/unmount
- `components/ResultPanel.tsx` — hidden until job reaches `done`; shows `<img>` from `output_urls[0]`; metadata row: clock icon + `{duration_seconds}s`, hash icon + `seed`, cube icon + `checkpoint`; download button uses `<a href=... download>`
- `components/ErrorBanner.tsx` — shown on `failed` state; displays `job.error`; "Try Again" button resets state to `idle`
- Wire form → `useJob.submit()` on submit; pass job state into `ResultPanel` and `ErrorBanner`

### Phase 4: Job History, Connection Status, and Polish

- `components/JobHistory.tsx` — right drawer or collapsible bottom panel; reads from `useJobHistory` hook (localStorage-persisted array of `{id, status, thumbnail_url, params, created_at}`); each row: 48×48 thumbnail (or status icon placeholder), status badge (`PENDING`/`RUNNING`/`COMPLETED`/`FAILED` — four distinct colors), relative time ("2 min ago")
- `hooks/useJobHistory.ts` — appends to history on each job completion; caps at 20 entries; exposes `clearHistory()`
- `components/ConnectionStatus.tsx` — top-right corner: polls `GET /api/health` every 10s; green dot + "Connected" or red dot + "Unreachable"; no polling backoff needed at this cadence
- `components/ApiKeyInput.tsx` — gear icon in header opens a small popover; password `<input>` pre-filled from localStorage; saves on blur
- Responsive layout: at `<768px`, sidebar collapses to a top horizontal scroll bar of dropdowns; result panel stacks below prompts
- `FastAPI integration`: mount `frontend/dist` as `StaticFiles` at `/ui` in `api/app/main.py`; add a `GET /ui` redirect to `/ui/index.html`; add `frontend/dist/` to `.gitignore`

---

## Technical Notes

### Stack Decisions

- **Vite over CRA**: CRA is unmaintained; Vite gives sub-second HMR and clean proxy config
- **Tailwind over CSS Modules or styled-components**: Utility-first keeps component files self-contained; consistent with the "no build-time CSS" requirement for a small app; no design token sync needed
- **Lucide React over Heroicons**: Tree-shakeable, maintained, better TypeScript types; same visual language as shadcn/ui if components are added later
- **Inter font via CSS import**: `@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap')` in `index.css`; no font download at build time
- **No UI component library (yet)**: v5 is too small to warrant Radix + shadcn setup cost; raw Tailwind + Lucide achieves the same result; migrating later is mechanical
- **localStorage for history and API key**: No backend state needed; history is best-effort and client-local; an API key stored in localStorage is acceptable for a single-user self-hosted tool
- **`apiFetch` wrapper, not Axios or React Query**: The API surface is five endpoints; the overhead of a data-fetching library is not justified; a 20-line wrapper is easier to audit

### Key File Paths

| Path                                           | Purpose                                             |
| ---------------------------------------------- | --------------------------------------------------- |
| `frontend/vite.config.ts`                      | Proxy `/api` → `:8000`, build output to `dist/`     |
| `frontend/src/hooks/useApi.ts`                 | Models + workflows fetch, shared `apiFetch` wrapper |
| `frontend/src/hooks/useJob.ts`                 | Job submission state machine + 2s polling           |
| `frontend/src/hooks/useJobHistory.ts`          | localStorage-persisted job history, capped at 20    |
| `frontend/src/components/Sidebar.tsx`          | Checkpoint, workflow, sampler, scheduler selectors  |
| `frontend/src/components/PromptForm.tsx`       | Positive + negative prompt textareas                |
| `frontend/src/components/SettingsPanel.tsx`    | Steps, CFG, seed, width, height controls            |
| `frontend/src/components/ResultPanel.tsx`      | Image display, metadata, download button            |
| `frontend/src/components/JobHistory.tsx`       | Recent jobs list with thumbnails and badges         |
| `frontend/src/components/ConnectionStatus.tsx` | Health poll, green/red indicator                    |
| `frontend/src/components/ApiKeyInput.tsx`      | API key popover, localStorage persistence           |
| `api/app/main.py`                              | Mount `StaticFiles("frontend/dist")` at `/ui`       |

### Local Dev Workflow

```bash
# Terminal 1: API + ComfyUI + LocalStack
docker compose up -d

# Terminal 2: React dev server (proxies /api to :8000)
cd frontend && npm install && npm run dev
# → http://localhost:5173

# Build static assets for FastAPI serving
cd frontend && npm run build
# → frontend/dist/ served at http://localhost:8000/ui
```

### Design Principles

The UI should feel like a professional creative tool, not a demo page. Specifics:

- Dark surface (`zinc-900` background, `zinc-800` panels, `zinc-700` borders) — image generation tools are used in dark environments
- Inter 400/500/600 only — no bold headings, no decorative type
- Icon + label pairs everywhere (never icon-only without tooltip)
- Sliders show their current value as a live number beside the track
- Skeleton loaders (animated `zinc-700` bars) while API data loads — no "Loading..." text
- Status badges use muted background tones: `emerald-900/50` text `emerald-400` for COMPLETED, `amber-900/50` text `amber-400` for RUNNING, `red-900/50` text `red-400` for FAILED

### Risks & Mitigations

| Risk                                                       | Mitigation                                                                                                     |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| CORS error in local dev if proxy misconfigured             | All API calls go through `/api` prefix; Vite proxy eliminates CORS; no `localhost:8000` direct calls in source |
| FastAPI `StaticFiles` conflicts with existing routes       | Mount at `/ui` after all API routes are registered; `GET /` remains the API root                               |
| Job history thumbnails link to expired presigned URLs (v1) | Use CloudFront URLs (v3) for durable thumbnails; in local dev, refetch on click                                |
| API key visible in DevTools localStorage                   | Acceptable for self-hosted single-user; document the risk; do not log the header server-side                   |
| `npm run build` must run before FastAPI can serve `/ui`    | Add `build:ui` to a top-level `Makefile` or `docker-compose build` step; document in README                    |

---

## Changelog

| Date       | Change        |
| ---------- | ------------- |
| 2026-03-27 | Initial draft |
