# S2 - Web UI Foundations - Design

Date: 2026-10-09
Status: Implemented on master (S2).
Source of truth: `../../2026-10-06-initial_rag_mvp_agent_project_context.md` (the "MD") and `2026-10-06-roadmap.md` (the "slices spec"). Where those disagree with this document on S2 topics, this document wins; where this document is silent, they govern.

## 1. Context

S2 stands up the `web/` frontend per the re-cut roadmap (slices spec §2, decision 5): a pure client-side SPA - Devias Kit / React / Redux on Vite. The MD's Next.js (MD §2, §24) was superseded on 2026-10-09: no SSR and no Node server; FastAPI stays the sole server, serving the JSON API.

Scope is exactly the slices spec's S2 row: landing; register/login/logout; projects list + create (team picked from the user's workspaces/teams), wired to the existing S1 API - nothing more. Every later slice pairs its backend work with its matching frontend part.

Environment (verified 2026-10-06): Node 24.14.1 / npm 11.20.0 on Windows 10. The SPA dev server runs on Vite's default port 5173; the API on uvicorn's default 8000 - hence the CORS work in §7.

## 2. Decisions (from the 2026-10-09 design round)

1. **Devias Kit basis**: the free `devias-io/material-kit-react` (MIT) is now Next.js-based; its Vite version exists only in the paid Devias Kit Pro. Decision: use the free kit as *design reference only* (palette, typography, spacing, auth-page layouts) and scaffold `web/` fresh with Vite. No template code is imported.
2. **JWT storage**: `localStorage`, mirrored into Redux state, with the XSS trade-off recorded in code (§6.1) and the httpOnly-cookie upgrade path in the backlog. Chosen for simplicity and refresh survival given a 24h token and no refresh-token backend.
3. **Testing**: Vitest + React Testing Library + MSW for the fast TDD loop (jsdom, mocked API), plus Playwright E2E against the real backend + Postgres for the literal "from a browser, all tested" gate. E2E is a separate `npm run e2e` command, not part of the default test gate.
4. **Data layer**: Redux Toolkit Query (RTK Query) for server state (projects, workspaces, teams) + a small `authSlice` for session state. Rationale in §6.2.

## 3. Stack and tooling

| Concern | Choice |
|---|---|
| Build | Vite 7, React 19, TypeScript strict |
| UI kit | MUI v7 components |
| Styling | Tailwind CSS v4 utilities alongside MUI theme |
| State | Redux Toolkit 2 - one store; RTK Query for server state, `authSlice` for session |
| Routing | React Router v7 library mode |
| Tests | Vitest + React Testing Library + MSW (jsdom); Playwright (Chromium) |
| Lint/format | ESLint (typescript-eslint, react-hooks, react-refresh) + Prettier |
| Type style | The free kit's: `Work Sans` for headings, `Inter` for body |

`web/` is a new top-level directory, sibling of `backend/`, keeping the future repo split a directory extraction (slices spec §3). Node/npm files never appear under `backend/`; Python never under `web/`.

```
web/
  src/
    app/            # Redux store, router, RequireAuth guard, base API client
    theme/          # MUI theme in the kit's palette; Tailwind entry CSS
    layouts/        # MarketingLayout, AuthLayout, DashboardLayout
    features/
      auth/         # authSlice, tokenStorage, login page, register page
      projects/     # projectsApi (RTK Query), ProjectsPage, CreateProjectDialog
      workspaces/   # workspacesApi, teamsApi; team picker used by the dialog
    lib/            # tokenStorage, error-message helper
  e2e/              # Playwright specs + server/DB bootstrap
```

npm scripts: `dev`, `build`, `preview`, `lint`, `test` (Vitest, run-scope default), `e2e` (Playwright).

## 4. Pages and UX

Devias Kit aesthetic throughout: generous whitespace, muted palette with one accent, rounded 12px cards, 1px subtle borders, plain professional English copy.

### 4.1 Landing `/` (MarketingLayout)

Hero: product name plus a one-sentence problem/solution pair ("Your documents, searchable by meaning - upload, ask, get grounded answers"). Two CTAs: **Get started** -> `/register`, **Sign in** -> `/login`. A short three-step "how it works" strip (Create a project -> Upload documents -> Ask questions). Just a wordmark and the two buttons; no marketing navbar. Fulfills MD §24 "landing page describing the problem/solution" without a full marketing site.

### 4.2 Login `/login` (AuthLayout)

Email + password form; submit button with busy state; link to `/register`. 401 renders the inline error "Invalid email or password". Authenticated visitors bounce to `/projects`.

### 4.3 Register `/register` (AuthLayout)

Email + password + password confirmation (client-side match check only; no email verification in the MVP). Success (201) lands the user directly in the app because the S1 API returns a token on register. 409 renders "That email is already registered" with a sign-in link.

### 4.4 Projects `/projects` (DashboardLayout)

The app home. Topbar with the user's email in a dropdown menu containing **Sign out**. Data table columns: Name, Visibility (Private/Public), Created. **Create project** opens a dialog with a **Team** picker: it loads `GET /workspaces`, then `GET /workspaces/{id}/teams` per workspace, and renders workspace > team options, preselecting the only team a single-user MVP registration creates - this satisfies "team picked from the user's workspaces/teams". Empty state: friendly "No projects yet" card with a create CTA. No row actions and no row navigation: view/edit/delete project UI is out of scope until S3+.

### 4.5 Loading and error states

RTK Query `isLoading` drives table skeletons. Form-level API failures (401/409/422) render inline under the form. Unexpected failures (network down) surface a global snackbar. Errors are announced to assistive tech via `aria-live`.

## 5. API data layer

### 5.1 Consumed S1 contract (exact)

| Endpoint | Used by | Notes |
|---|---|---|
| `POST /auth/register` | register page | 201 `{access_token, token_type}`; 409 registered; 422 validation |
| `POST /auth/login` | login page | 200 `{access_token, token_type}`; 401 bad credentials |
| `POST /auth/logout` | sign-out menu | 204; best-effort, local session cleared regardless |
| `GET /users/me` | auth bootstrap | 200 `{user_id, email}`; 401 -> clear + `/login` |
| `GET /workspaces` | team picker | 200 `[{id, name}]` |
| `GET /workspaces/{id}/teams` | team picker | 200 `[{id, name, workspace_id}]`; 404 not a member |
| `POST /projects` | create dialog | 201 `ProjectOut`; 404 team not found |
| `GET /projects` | projects page | 200 `[ProjectOut]`; includes the registration Default project |

`ProjectOut = {id, name, is_public, created_at}`.

### 5.2 Architecture

One RTK Query `createApi` instance ("base API client" in `src/app/`) over `fetchBaseQuery`, reading `VITE_API_BASE_URL` (default `http://localhost:8000`) and injecting `Authorization: Bearer <token>` from the store. Feature slices (`projectsApi`, `workspacesApi`, `teamsApi`) inject endpoints with cache tags; creating a project invalidates the projects tag so the list refetches.

`authSlice` is *session* state, not server cache: `{token: string | null, user: {id, email} | null, status: "idle" | "booting" | "busy"}`. Server state lives only in RTK Query; nothing else caches API responses.

### 5.3 Deep-module boundaries

A page component never constructs a URL, parses a response body, or reads localStorage directly:

- `lib/tokenStorage.ts` - the only module touching localStorage (`loadToken`, `saveToken`, `clearToken`).
- `src/app/` base API client - hides fetch, auth header, error normalization; exposes a `getErrorMessage(err)` helper mapping FastAPI's `{detail}` shape to a user-facing string.
- `authSlice` - hides bootstrap semantics; pages dispatch actions and read selectors.
- RTK Query endpoints - hide caching and refetching.

## 6. Auth flow

### 6.1 Token lifecycle (localStorage + Redux)

`tokenStorage.ts` carries a comment recording the decision and its cost: a script injected via XSS can read the token from localStorage; S2 renders no user-supplied HTML so the attack surface is the app's own code, and the httpOnly-cookie upgrade is contained to this module plus the base query (backlog). The `authSlice` is the single source of truth at runtime; localStorage is only the persistence layer, read at boot and written on login/register.

### 6.2 Bootstrap, login, register, logout

- **Bootstrap**: on app mount with a stored token, `bootstrapAuth` dispatches `GET /users/me` with that token. 200 -> hydrated user, routes render. 401 -> clear token, land on `/login`. The stored token is validated, never trusted.
- **Login / register**: thunks store the token returned by `POST /auth/login` / `POST /auth/register`, then hydrate the user via `GET /users/me` (auth responses carry no user id; register needs no login call), then redirect to `/projects`. Failure paths: 401 -> "Invalid email or password"; 409 -> "That email is already registered" + sign-in link; network failure -> generic retryable banner.
- **Logout**: `POST /auth/logout` (revokes the jti server-side), then clear token + user, reset the RTK Query cache (`api.util.resetApiState()`), redirect to `/`. If the revocation call fails, the local session is still cleared - revocation is best-effort since the token expires in 24h anyway.
- **Routing**: `RequireAuth` guard reads token + user; unauthenticated hits to `/projects` redirect to `/login`. Unprotected: `/`, `/login`, `/register`. Unknown paths fall back to `/`. A `booting` status renders a full-page splash instead of redirect-flashing.

## 7. CORS backend change (S2's backend half)

`app/main.py` gains `CORSMiddleware`: `allow_origins=settings.cors_origins`, `allow_credentials=False` (pure Bearer-header auth, no cookies), `allow_methods=["*"]`, `allow_headers=["*"]`. New setting `cors_origins: list[str]` (`RAG_CORS_ORIGINS`, default `["http://localhost:5173"]`) in `app/core/config.py`. Tested with pytest: the settings default, and a preflight `OPTIONS` request echoing the allowed origin.

## 8. Testing strategy

TDD throughout: every plan task names its failing test first, then the implementation.

1. **Vitest + RTL + MSW** (`npm test`) - the TDD inner loop, jsdom with mocked API:
   - `authSlice` reducer/thunk tests: token lifecycle, bootstrap 401 -> cleared, boot splash.
   - API behavior via MSW: login 200 stores token; login 401 inline error; register 409 + sign-in link; logout calls `POST /auth/logout`, resets cache; register 422 validation error.
   - Projects: list renders rows (incl. the Default project); create dialog posts `{name, team_id}`, list refetches; team picker loads workspaces -> teams cascade.
   - Route guards: `/projects` unauthenticated -> `/login`; `/login` authenticated -> `/projects`; unknown path -> `/`.
   - A11y sanity: labeled forms, `aria-live` error announcement.
   - Suite rule mirrors the backend: every test file runs, no skipped tests.
2. **Playwright E2E** (`npm run e2e`, separate from the default gate) - the "from a browser" proof: real Chromium, uvicorn backend, Vite preview/dev server, the compose Postgres. A fixture boots a dedicated `rag_e2e` database (same migration bootstrap as pytest) and truncates users between tests; each test registers a fresh user, which also exercises the 409 path. Specs:
   - Full journey: register -> land on `/projects` (Default project visible) -> create project -> see it in the list -> sign out -> landing.
   - Logged-out enforcement: after sign-out, the projects fetch 401s (a genuinely revoked jti), and protected routes redirect.
3. **Manual visual check** - AGENTS.md holds the UI to a high visual standard: spacing, alignment, typography, consistency at 390px, 768px, and 1280px widths.

Verification (backend, unchanged): `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`. Frontend: `npm run lint`, `npm test`, `npm run build`, and at implementation end `npm run e2e`.

## 9. Risks and accepted costs

- **localStorage XSS exposure** - documented in code and backlog; upgrade contained to `tokenStorage.ts` + base query.
- **Free-kit-as-reference fidelity** - layouts are hand-built, so "looks like Devias" is a judgment call; the bar is clean, consistent MUI, not pixel-matching their demo.
- **Playwright flake on Windows** - real browser + servers + DB; mitigated by generous per-test timeouts, serial mode, and keeping E2E out of the default gate.
- **CORS default in settings** - `["http://localhost:5173"]` is a dev convenience; production deployment overrides `RAG_CORS_ORIGINS` (out of scope).

## 10. Out of scope (S2 bounds)

Project detail/edit/delete UI, public-projects browsing UI, upload/query UI (S3+S4), answer UI (S6), profile page, team management UI, dark-mode toggle, i18n, any auth backend change beyond §7's CORS, production deployment, password reset, refresh tokens, httpOnly cookies.

## 11. Done when

Register -> login -> logout -> list/create projects from a browser, all tested: the Vitest suite covers every flow above, the Playwright journey passes against the real backend + Postgres, the backend suite still passes with the CORS change, and the three-width manual visual check finds no glaring defects.