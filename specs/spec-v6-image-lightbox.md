---
version: 6
name: image-lightbox
display_name: "Image Lightbox"
status: complete
created: 2026-03-28
depends_on: [5]
tags: [frontend, ui]
---

# Image Lightbox

## Why (Problem Statement)

> As a user, I want to click on a generated image (in either the result panel or the job history) so that I can view it full-size without leaving the app.

### Context

- The `ResultPanel` renders the generated image capped at `max-h-[60vh]` — large or portrait images are cropped
- The `JobHistory` panel shows 12×12 thumbnails with no way to inspect the full image
- Users currently must use "Download image" to see the full output, which is cumbersome
- Both `JobHistory.tsx` and `ResultPanel.tsx` render `<img>` tags that are not interactive

---

## What (Requirements)

### User Stories

- **US-1**: As a user, I want to click the image in the result panel so that I can see the full-size generated image
- **US-2**: As a user, I want to click a thumbnail in the history panel so that I can view that job's output full-size
- **US-3**: As a user, I want to press ESC or click outside the image to dismiss the lightbox

### Acceptance Criteria

- AC-1: Clicking the result image opens an overlay showing the full-resolution image
- AC-2: Clicking any thumbnail in job history opens an overlay for that image
- AC-3: Pressing ESC dismisses the overlay
- AC-4: Clicking the backdrop (outside the image) dismisses the overlay
- AC-5: The overlay traps scroll and prevents background interaction while open
- AC-6: The cursor is `pointer` on clickable images

### Out of Scope

- Multi-image carousel (only one image per job currently)
- Zoom/pan within the lightbox
- Keyboard navigation between jobs

---

## How (Approach)

### Phase 1: Lightbox Component

- Create `frontend/src/components/Lightbox.tsx` — full-screen overlay, renders `<img>` centered, backdrop click closes, ESC key closes, `overflow-hidden` on body while open
- Accept props: `url: string`, `onClose: () => void`
- Use a React portal (`createPortal`) to render outside the component tree

### Phase 2: Wire Up ResultPanel

- Add `useState<string | null>` for `lightboxUrl` in `ResultPanel.tsx`
- Wrap the result `<img>` in a `<button>` (or add `onClick` + `cursor-pointer`) to set `lightboxUrl`
- Render `<Lightbox>` when `lightboxUrl` is set

### Phase 3: Wire Up JobHistory

- Add `onImageClick?: (url: string) => void` prop to `JobHistory`
- Call it when the thumbnail `<img>` is clicked
- Lift lightbox state to `App.tsx` (or the parent that renders both panels) and pass down

### Phase 4: Tests

- Write a Vitest + React Testing Library test for `Lightbox.tsx`: renders with a URL, ESC key fires `onClose`, backdrop click fires `onClose`
- Tests use real DOM rendering — no mocks

---

## Technical Notes

### Architecture Decisions

- Portal-based lightbox avoids z-index battles with the sidebar and panel layout
- Lifting state to `App.tsx` is the simplest path; `JobHistory` already receives `history` and `onClear` from `App.tsx`

### Dependencies

- `react-dom` (`createPortal`) — already available
- Vitest + React Testing Library — check if already configured in `frontend/`

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| CloudFront signed URLs expire | Lightbox opens immediately on click — URL is already valid at that point |
| History thumbnails may not have a full-res URL separate from thumbnail | Both `thumbnail_url` and full-res URL come from the same signed URL today — use as-is |

---

## Open Questions

1. Should the lightbox show the prompt text or metadata below the image, or just the image?

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-28 | Initial draft |
