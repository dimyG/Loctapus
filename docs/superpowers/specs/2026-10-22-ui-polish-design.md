# UI polish round - Design

Date: 2026-10-22
Status: Design approved in chat (2026-10-22 round, including one user ruling: the raw-file
endpoint is in scope). This written spec is pending the user's review; not yet implemented.
Source of truth: `../../2026-10-06-roadmap.md` and this document. Where they disagree on this
slice's topics, this document wins; where it is silent, they govern.
The 2026-10-21-ui-mui-templates spec stays frozen; this round restyles on top of it.

## 1. Context and goal

The user reviewed the running UI and filed ten remarks. This round addresses them: mostly pure
frontend restyling with exactly one approved backend addition (a read-only raw-file endpoint that
remark 1 needs). No pipeline, schema, or routing changes otherwise.

Done-when: on the compose stack, a signed-in user can open an uploaded PDF in a new browser tab
from the sources list, the page toolbars clear the topbar, the topbar dropdown carries a
"Project" label, chat looks like ChatGPT inside our template, no form label collides with an input
border (light and dark), in-flight uploads show a spinner in their status chip, the landing page
carries the new marketing copy with one centered "Get started" button, and the app is named
"Loctapus" with the octopus logo everywhere the wordmark appears. All suites green.

## 2. Decisions

1. **Filenames open the stored file in a new tab (remark 1).** New read-only endpoint
   `GET /api/projects/{project_id}/uploads/{upload_id}/raw` returns the item's stored bytes.
   The SPA cannot link to it directly (browser navigation sends no `Authorization` header), so
   the UI fetches it with the bearer token, makes a blob URL, and `window.open`s it. PDFs render
   in the tab; DOCX cannot render in any browser and downloads instead (inherent, recorded as
   backlog).
2. **Page toolbars get top spacing (remark 2).** `pt: 3` on the header `Stack` of the projects,
   sources, and file-upload pages so the search and primary controls clear the topbar's bottom
   border.
3. **The topbar dropdown gets a "Project" label (remark 3).** Following the dashboard
   template's selector (the user's reference screenshot): the `Select`'s closed rendering
   becomes two lines inside a row with a small rounded leading avatar (the project name's first
   letter) - the project name on line one and a `caption` "Project" (`text.secondary`) on line
   two. Menu items stay single-line names; the select keeps its accessible name.
4. **Chat gets the ChatGPT layout inside our template (remark 4).** Centered 760px column:
   scrolling thread, user questions in gray rounded bubbles aligned right, answers as plain
   full-width text followed by a row of small subtle source chips (each opening its chunk in a
   dialog), and a rounded composer whose "Ask" action sits inside at the bottom right. Active,
   inactive, and sending states are all clearly visible; no label sits on a background that
   swallows it.
5. **The floating label never crosses the input border (remark 5).** Root cause: the theme draws
   the border on `MuiOutlinedInput` root with `notchedOutline: { border: "none" }`, so the label
   gets no notch gap, and a 3px focus outline on the root runs straight through it. Fix: restore
   the border to `notchedOutline`, express hover/focus as border-color changes, drop the root
   focus outline, and drop the `MuiFormLabel` `marginBottom` that pushes the floating label onto
   the border path. Applies to every form (login, register, create-project dialog, search
   fields) because it is a theme fix.
6. **In-flight uploads show a spinner in their status chip (remark 6).** New
   `UploadStatusChip` wraps the existing `statusChip` mapping and prepends a 12px
   `CircularProgress` while the status is non-terminal.
7. **Hero shows one centered "Get started" button (remark 7).** The "Sign in" button leaves the
   hero (the navbar keeps its own); "Get started" centers under the copy.
8. **The landing page carries the new marketing copy (remark 8).** New title and subtitle, a
   four-step section (steps 3 and 4 marked "Coming"), and a four-card value section.
9. **The app is named "Loctapus" (remark 9).** Wordmark `Loctapus` everywhere the "RAG"
   wordmark appears today: document title, marketing topbar and footer, auth frame, both
   sidenav brand areas, about copy, and the tests that assert them. (The user wrote
   "loctapus"; this spec uses title case - flagged for the spec review.)
10. **The octopus logo is the brand mark, the favicon package is the tab icon (remark 10,
    amended 2026-10-22).** `D:\Downloads\Blue Chat Octopus Logo.png` is committed as
    `web/public/logo.png` (a 28px `img` beside each wordmark, 4 spots). Verified 2026-10-22: a
    1254x1254 RGBA PNG with a fully transparent background (corner alpha 0), solid blue body
    (~#0A67FD) - a chat-bubble octopus head with three white typing dots and five curled
    tentacles; bold flat shapes stay legible at 28px on both light and dark surfaces. The
    favicon comes from the provided package `D:\Downloads\favicon_io.zip`, extracted unmodified
    into `web/public/` (`favicon.ico`, `favicon-16x16.png`, `favicon-32x32.png`,
    `apple-touch-icon.png`, `android-chrome-192x192.png`, `android-chrome-512x512.png`, and
    `site.webmanifest` with its empty `name`/`short_name` set to "Loctapus"), replacing
    `favicon.svg`.

## 3. Backend: the raw-file endpoint

`backend/app/sources/router.py`, `backend/app/sources/service.py`.

- Service: `get_upload_item(*, db, project_id, upload_id) -> SourceItem | None` joins through
  the upload source like `list_uploads` does and returns the item or None (404 at the router).
- Route `GET /projects/{project_id}/uploads/{upload_id}/raw`, `response_class=Response`:
  1. `get_project_visible_to_user` (same check as the list route); None -> 404 "project not
     found".
  2. `get_upload_item`; None -> 404 "upload not found".
  3. `storage.get_object(key=item.raw_object_key)`; `ObjectNotFoundError` -> 404 "file not
     found", `StorageUnavailableError` -> 503 "Could not load the file. Please try again."
  4. `Response(content=..., media_type=item.content_type, headers={"Content-Disposition":
     f'inline; filename="{item.filename}"'})`. `inline` so the tab renders PDFs instead of
     forcing a download; the media type is the stored one (`application/pdf` or the DOCX mime),
     never a client header's.
- No new schema, table, or migration; auth via the existing `get_current_user`.

Tests (backend suite): 401 unauthenticated, 404 invisible project, 404 foreign/unknown upload
id, 503 storage failure, and the happy path asserting body bytes, media type, and the
inline disposition header.

## 4. Web: sources list opens files

- `web/src/features/uploads/uploadsApi.ts`: `getUploadRaw` endpoint
  (`GET /projects/{projectId}/uploads/{uploadId}/raw`, `responseHandler` returning the response
  blob).
- `web/src/features/sources/SourceItemsTable.tsx`: the filename cell keeps its link look but
  becomes a click handler (`component="button"`): dispatch the raw fetch, `URL.createObjectURL`
  on the blob, `window.open(url, "_blank", "noopener")`, revoke the URL after the open, and on
  failure surface a `Snackbar` "Could not open the file." with a retry action. Nothing else in
  the table changes in this commit (the spinner arrives in its own).

## 5. Web: theme form fix

`web/src/theme/customizations/inputs.tsx`.

- `MuiOutlinedInput.root`: drop the root `border`, the `3px` focus `outline`, and the root
  `borderColor` hover. Keep the 8/12px padding and the light/dark height variants as they are.
- `notchedOutline`: `border: 1px solid <palette.divider>` so the floating label gets its notch
  gap; hover on the root switches it to `gray[400]` (light) / `gray[500]` (dark); focus switches
  it to `brand[400]`.
- `MuiFormLabel.root`: drop `marginBottom: 8` (it shifts the floating label down onto the
  border); keep the caption typography.
- Verify visually in both color modes on the login form, register form, create-project dialog,
  and the projects/sources search fields: no label/border crossing at rest, hover, or focus.

## 6. Web: chat page (ChatGPT layout on our template)

`web/src/features/chat/ChatPanel.tsx`.

- **Column**: `mx: auto`, `width: 100%`, `maxWidth: 760`, `display: flex`, `flexDirection:
  column`, height `calc(100dvh - 176px)` (topbar 56 + spacer 56 + container bottom padding 48 +
  breathing 16; final offset tuned at implementation) so only the thread scrolls.
- **Thread**: `flexGrow: 1`, `overflowY: auto`, turns spaced; auto-scroll behavior kept as is.
- **Question**: `body2` text inside a rounded bubble (`borderRadius: 18px`, `px: 2`, `py: 1`,
  `backgroundColor: action.hover`), aligned right, `maxWidth: 80%`.
- **Answer**: plain `body1` `pre-wrap` text, full width (no bubble, no avatar). The sources
  become small subtle labels (amended 2026-10-22): a wrapping row of `Chip size="small"
  variant="outlined"` chips labeled `[i] filename`, taking a fraction of the accordion's
  space; clicking a chip opens a small dialog titled with the full `[i] filename > path` label
  and showing the chunk text, so the grounding stays one click away without crowding the
  thread. Pending answer: a small `CircularProgress` next to "Thinking..." in `text.secondary`.
- **Composer**: one rounded outlined container (`border: 1px solid divider`, `borderRadius:
  <theme>`, `p: 1`) holding the multiline `TextField` (label "Ask a question" kept, 2 min
  rows, no shadow) and the Ask action inside at its bottom right.
- **Ask action**: a 40px circular `IconButton` (`ArrowUpwardRoundedIcon`, `aria-label="Ask"`,
  so the e2e `getByRole("button", { name: "Ask", exact: true })` keeps working). Active: the
  template's contained-primary skin. Inactive (empty input or sending): `gray[100]`/`gray[800]`
  fill with a `gray[500]` icon via `&.Mui-disabled`, so the disabled state reads clearly
  instead of text-on-gradient. While sending, the icon swaps to a 16px `CircularProgress`.
  Enter still submits, Shift+Enter still newlines, both fields disable while pending.

## 7. Web: everything else

- **Status chip spinner** (remark 6): `web/src/features/uploads/UploadStatusChip.tsx` renders
  `Chip` with the existing `statusChip(status)` props plus a 12px `CircularProgress` in the icon
  slot while `!isTerminal(status)`. `SourceItemsTable` switches to it (both the sources and
  file-upload pages inherit it through the shared table).
- **Spacing** (remark 2): `pt: 3` on the header `Stack` in `ProjectsPage`, `SourcesPage`, and
  `FileUploadPage`.
- **Dropdown label** (remark 3): `ProjectSelect`'s `renderValue` returns a row with a small
  rounded `Avatar` (the project name's first letter) and a two-line block - the project name
  (`body2`) over a `caption` "Project" (`text.secondary`) - matching the dashboard template's
  selector from the user's reference screenshot. The "Select project" / "No projects"
  placeholders keep their single-line rendering.
- **Landing** (remarks 7+8): title "Chat with your company's knowledge base"; the given
  subtitle verbatim; hero buttons reduce to one centered contained "Get started"; new sections
  below:
  - "How it works": four step cards - 1 "Connect your knowledge base" ("Upload files, connect
    cloud storages and websites, and keep them in sync."), 2 "Chat in our interface" ("Ask
    questions inside our web app; it is the simplest way to use the service."), 3 "Deploy an
    agent" ("Give an agent access to your knowledge base where your users need it: your docs
    page, your app, Slack, your support desk."), 4 "Analyze" ("See what people ask, where your
    agent shines, and where it struggles."). Steps 3 and 4 carry a "Coming" chip and muted
    styling.
  - "Built for your team": four value cards - "Answer complex customer questions" ("Ground
    every answer in your own documents, with the sources to prove it."), "Give your teams a
    personal assistant" ("An assistant that knows your product, your processes, and your
    terminology."), "Keep your knowledge base always up to date" ("Re-asking always reads the
    latest version of your sources."), "AI agents custom to your enterprise" ("Spin up an
    agent wherever your users already are, on top of your own knowledge."). Copy is the
    implementing agent's draft from the user's outline; flagged for the spec review.
- **Name and logo** (remarks 9+10): `Loctapus` wordmark plus a 28px `img` of
  `web/public/logo.png` (committed from the user's file) in the marketing topbar, the marketing
  footer, the auth frame, and both sidenav brand areas; `index.html` title "Loctapus" and the
  standard favicon link set pointing at the extracted package files (`favicon.ico`,
  `favicon-32x32.png`, `favicon-16x16.png`, `apple-touch-icon.png`, `site.webmanifest`), the
  old `favicon.svg` deleted; about page copy updated; every test that asserts "RAG" is updated
  with it.

## 8. Task DAG

Independent tasks (parallelizable):

- T1 Backend raw endpoint (section 3) plus its tests.
- T2 Theme form fix (section 5).
- T3 Name, logo, favicon, and their tests (section 7, last bullet).
- T4 Landing content and hero button plus tests (section 7).
- T5 Toolbar spacing on the three pages (section 7).
- T6 ProjectSelect label (section 7).
- T7 UploadStatusChip plus tests (section 7).
- T8 Chat panel redesign plus tests (section 6).

Dependencies:

```
T1 ──────────────► T9 (sources table opens files; needs T1, same file as T7)
T2 T3 T4 T5 T6 T7 T8 ──► independent of each other; T9 also after T7 (same file)
all ──────────────► T10 docs refresh (system overview + backlog)
```

- T9: section 4 (touches `SourceItemsTable.tsx`, which T7 also touches - order T7 first).
- T10: `docs/2026-10-19-system-overview.md` gains the endpoint row, the rename, and the new UI
  notes; `docs/backlog.md` records the follow-ups with commit links.

## 9. Testing and verification

- Unit (web): update `MarketingFrame`, `AuthFrame`, `AboutPage`, `App` tests for the rename and
  logo; new `UploadStatusChip` tests; `SourceItemsTable` tests for the open-in-tab handler
  (blob fetch mocked, `window.open` spied, failure snackbar); `ChatPanel` tests for the
  composer's active/inactive/sending states; `LandingPage` tests for the new sections.
- Unit (backend): the five endpoint cases from section 3.
- e2e: `journey.spec.ts` and `enforcement.spec.ts` keep passing unchanged (the Ask button and
  the "Ask a question" label keep their accessible names); the journey already exercises
  upload, indexing, and asking.
- Verification before done: backend `ruff check .`, `ruff format --check .`, `mypy app tests`,
  `pytest`; web `eslint`, `tsc`, `vitest` run, and Playwright against a live stack.

## 10. Out of scope

- DOCX in-browser preview (would need client-side conversion) - the raw tab downloads it.
- Project edit/delete, cross-project sources listing, and the agent/analytics features the
  landing copy teases - each is a future slice, some already in the backlog.
- No behavior changes to upload, ingestion, retrieval, or answers beyond the added endpoint.