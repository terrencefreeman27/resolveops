# ResolveOps UI redesign — visual direction

Branch `feat/ui-redesign`. This records what was actually inspected, which patterns were adapted, and the token system the frontend now uses. Product context was inferred from the written brief (no interview was possible in this session).

## What was inspected

All four pages were loaded with headless Chromium (playwright-core) at 1440×900; full-page captures were saved to `docs/design/references/` and are kept locally only (not committed — they are third-party pages; see `.gitignore`). A selection of after-redesign screenshots is in `docs/design/screenshots/`. Embedded product images were listed in `references/images.json`; the most relevant ones were downloaded with `curl` and viewed, but **not committed** (they are third-party assets; only our own page captures are kept, as research).

| Reference | Result | What I could actually see |
|---|---|---|
| intercom.com/helpdesk/inbox | Loaded (200) | Marketing page with product renders: dark icon rail far left, a light inbox-list column ("Your Inbox", views with counts), a conversation list with avatar + name + one-line preview + relative time, the conversation in the centre, and a right "Details" panel with collapsible sections (LINKS, CONVERSATION ATTRIBUTES, USER DATA) of label/value rows. A Copilot render shows "15 relevant sources found" as a compact icon + title list, numbered inline citation markers in an answer, and a small popover with the source title, source type/author/age and the supporting passage. |
| intercom.com/help/…/the-inbox-explained | Loaded (200) | Help-article screenshots: the profile menu in the bottom-left of the dark rail groups account items (theme, language, workspace, help, log out); ⌘K action menu; table layout; filter button. |
| linear.app/docs/triage | Loaded (200) | Mostly docs prose in Linear's dark docs theme. The embedded Triage image (downloaded and viewed) shows a compact list: title on line one, source/requester with a small glyph on line two, identifier and relative time right-aligned in muted text — no coloured badges per row. |
| langfuse.com/docs/observability/overview | First attempt failed (`net::ERR_INTERNET_DISCONNECTED`); a retry with a hard timeout loaded (200) | The full-page capture is dominated by docs text and a cookie banner. The embedded trace screenshot (downloaded and viewed) shows a nested observation tree with per-step durations, a selected step opening a detail pane with Input/Output blocks, small metric chips (latency, session, env), and a collapsed "Graph" section. |

I did not inspect any product demo videos.

## Patterns adapted (not copied)

- **Intercom (primary):** compact dark navigation rail with the account menu at the bottom; three-pane workspace (inbox list · request · context); context panel as titled, collapsible label/value sections; sources as a compact list that opens the supporting passage; numbered citation markers next to the draft. No Intercom branding, colours, illustrations or assets are used.
- **Linear:** inbox rows ordered subject → customer → preview → metadata, with status shown as one small dot + word only when it carries information, muted relative time, and no stack of coloured badges.
- **Langfuse:** the execution timeline becomes a step list with durations and per-step expandable payloads (tool arguments and results), behind one "Execution details" disclosure, so the decision stays on top and the mechanics are one click away.

## ResolveOps direction

Calm, precise, light work surfaces framed by a near-black rail. One teal accent reserved for primary actions, selection and focus. Information is ordered by the reviewer's decision: what was asked → what we propose → what will happen if approved → why (evidence) → how (execution). Warnings stay visible; policy mechanics, scores, tool payloads and history move into disclosures and contextual help.

## Tokens (`frontend/src/index.css`, `@theme`)

Colour (contrast measured against the surface it sits on):

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--color-fg` | #171c1f | primary text | 17.2:1 on white |
| `--color-fg-muted` | #4a5459 | secondary text | 7.8:1 white, 7.2:1 canvas |
| `--color-fg-subtle` | #5f6a6f | metadata, captions | 5.6:1 white, 5.1:1 canvas, 4.9:1 selected row |
| `--color-surface` | #ffffff | request pane, cards | |
| `--color-canvas` | #f5f6f6 | inbox and context panels | |
| `--color-sunken` | #eef0f0 | wells, hover on canvas | |
| `--color-line` / `--color-line-strong` | #e3e6e7 / #cdd3d5 | dividers / control borders | |
| `--color-rail` / `--color-rail-fg` | #12181b / #aab4b8 | navigation rail | 8.5:1 |
| `--color-accent` | #0f766e | primary button, focus ring, selection | 5.5:1 white text on accent |
| `--color-accent-strong` | #0b5d56 | hover, accent text on tint | 6.8:1 on accent-soft |
| `--color-accent-soft` | #e7f2f0 | selected row, citation markers | |
| `--color-warn` / `--color-warn-soft` | #8a4b08 / #fdf5e6 | needs attention, stale | 6.3:1 |
| `--color-danger` / `--color-danger-soft` | #a8261d / #fdf1ef | errors, reject | 6.4:1 |
| `--color-ok` | #1d6b3c | completed | 6.5:1 |

Type: system UI sans for everything; monospace only for ids, ticket numbers and tool payloads. Scale (rem-fixed, ~1.15 ratio): 11 / 12 / 13 / 14 (UI body) / 15 (customer message and draft reply, 1.6 line-height) / 18 / 20 (request title). Tabular numerals for counts and durations.

Spacing: 4px base; the UI uses steps 1, 1.5, 2, 3, 4, 5, 6, 8 (4–32px). Radii: `--radius-sm` 4px (chips), `--radius-md` 6px (controls), `--radius-lg` 10px (cards, popovers), `--radius-xl` 14px (dialogs). Shadows: `--shadow-xs` hairline lift for cards, `--shadow-pop` for menus/popovers, `--shadow-sheet` for dialogs and drawers; all offset with soft blur.

Motion: 120–180ms colour/opacity transitions on hover and disclosure; menus fade/scale 4% from their trigger; all disabled under `prefers-reduced-motion`.

Icons: `lucide-react` (pinned 1.61.0), 16px in controls, 18px in the rail, 1.75 stroke throughout. Icon-only buttons always carry `aria-label` and a tooltip `title`.

## Layout

- ≥1280px: rail 56px · inbox 300–320px · request (fluid) · context 320–352px, each pane scrolls independently; the approval bar is a non-scrolling footer of the request pane, so it never covers content.
- 1024–1279px: rail · inbox · request; the context panel opens as a right-hand drawer from a "Details" button.
- <1024px: the rail becomes a top strip; Inbox / Request / Details tabs switch between full-width panes. Selecting or running a request jumps to the Request tab.
