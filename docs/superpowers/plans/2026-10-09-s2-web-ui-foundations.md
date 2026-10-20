# S2 - Web UI Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up `web/` - a React/Redux SPA on Vite in the Devias style - wired to the existing S1 API: landing, register/login/logout, projects list + create, all tested (Vitest + Playwright), plus the backend CORS change the SPA needs.

**Architecture:** One RTK Query `api` over a `fetchBaseQuery` (base URL + Bearer header) owns server state (projects, workspaces, teams); a small `authSlice` owns session state (token persisted through `tokenStorage`, user, status). React Router with a `RequireAuth` guard plus an app-mount bootstrap that validates the stored token via `GET /users/me`. The backend adds `CORSMiddleware` with a settings-driven origin list.

**Tech Stack:** Vite 7, React 19, TypeScript strict, MUI 7, Tailwind 4, Redux Toolkit 2 (RTK Query), React Router 7, Vitest + React Testing Library + MSW, Playwright, ESLint + Prettier. Backend: FastAPI's built-in `CORSMiddleware`, no new dependencies.

**Spec:** `../specs/2026-10-09-s2-web-ui-foundations-design.md` (the plan argues from the spec; executors read both).

## Global Constraints

- Backend verification, unchanged: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest` - all from `backend/`, all green.
- Backend rules: keyword-only parameters (`PLR0917`), line length 110, docstrings on every module/class/function (alembic scripts exempt).
- Frontend: TypeScript strict, no `any`; ESLint with `--max-warnings 0`; Prettier with `printWidth: 100`; every test file runs, no `.skip`/`.only`/`.todo`.
- `npm test` runs Vitest only (jsdom); Playwright E2E is a separate `npm run e2e` and never part of the default gate.
- Vite dev server on port 5173 (the backend CORS default origin). API base default `http://localhost:8000` via `VITE_API_BASE_URL`. E2E uses uvicorn on 8001 and `VITE_API_BASE_URL=http://localhost:8001` against a dedicated `rag_e2e` database.
- localStorage key `"rag.accessToken"`; `src/lib/tokenStorage.ts` is the only module that touches localStorage, and carries the XSS-tradeoff comment (spec §6.1).
- SPA only: no SSR, no Node server; FastAPI is the only server.
- Copy: plain professional English. Devias aesthetic: `Work Sans` headings, `Inter` body, 12px rounded cards, 1px subtle borders, accent `#5664D2`.
- Windows environment; Python venv at `.venv/Scripts/python.exe`; Node 24.14.1 / npm 11.20.0.
- Backend API contract (spec §5.1): register 201 `{access_token, token_type}`; login 200 same; logout 204; `GET /users/me` `{user_id, email}`; `GET /workspaces` `[{id, name}]`; `GET /workspaces/{id}/teams` `[{id, name, workspace_id}]`; `POST /projects` 201 `{id, name, is_public, created_at}`; `GET /projects` the list form. 422 body is FastAPI's `{detail: [...]}`.

## Review Focus

Failure modes the spec implies but whose tasks could under-exercise; each is pinned by a test in the owning task.

1. **API unreachable mid-session** (fetch rejects): forms show a retryable message, pages show a snackbar with retry - Task 6 (`login network failure`) and Task 9 (`projects network failure -> snackbar + retry`).
2. **Double-submit while a request is in flight**: submit/Create buttons disable while pending - Task 6 (`submit disabled while pending`), Task 7 (same), Task 10 (`Create disabled while pending`).
3. **Backend 422 validation** (e.g. a password under 8 chars passing client checks): a friendly inline message, never a raw dump - Task 7 (`422 -> friendly message`) and Task 10 (`422 -> inline dialog error`).
4. **Stale stored token** (expired/revoked while away): bootstrap 401 clears storage and lands on `/login`, never a crash or a redirect flash - Task 4 (`bootstrap 401 clears`) and Task 5 (`booting renders splash, guard redirects`).
5. **Team-picker cascade failure** (stale workspace, 404 teams): an inline dialog error, not a silently empty select - Task 10 (`404 -> inline dialog error`).

---

### Task 1: Backend CORS middleware

**Files:**
- Modify: `backend/app/core/config.py` (add `cors_origins`)
- Modify: `backend/app/main.py` (add middleware)
- Test: `backend/tests/test_cors.py` (new), `backend/tests/test_config.py` (extend)

**Interfaces:**
- Consumes: `Settings` / `get_settings` from `app/core/config.py`.
- Produces: `Settings.cors_origins: list[str]`, default `["http://localhost:5173"]`, env `RAG_CORS_ORIGINS` (JSON list). The SPA on 5173 can call the API on 8000/8001.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_config.py`, add:

```python
def test_cors_origins_default() -> None:
    """CORS defaults to the Vite dev origin."""

    assert Settings(_env_file=None).cors_origins == ["http://localhost:5173"]


def test_cors_origins_env_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """RAG_CORS_ORIGINS parses as a JSON list of origins."""

    monkeypatch.setenv("RAG_CORS_ORIGINS", '["https://app.example.com"]')
    assert Settings(_env_file=None).cors_origins == ["https://app.example.com"]
```

In `backend/tests/test_cors.py`:

```python
def test_preflight_allows_dev_origin(client: TestClient) -> None:
    """Preflight from the Vite origin is answered with the echoed ACAO header."""

    response = client.options(
        "/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_preflight_rejects_unknown_origin(client: TestClient) -> None:
    """Preflight from an origin outside the list gets no ACAO header."""

    response = client.options(
        "/health", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in response.headers


def test_get_echoes_allowed_origin(client: TestClient) -> None:
    """A simple GET from an allowed origin carries the ACAO header."""

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_cors.py tests/test_config.py -k cors -v` (from `backend/`)
Expected: FAIL - `test_cors.py` fails (`access-control-allow-origin` absent), config tests fail with `AttributeError: cors_origins`.

- [ ] **Step 3: Implement**

`config.py`: add `cors_origins: list[str] = ["http://localhost:5173"]` to `Settings` (JSON-list parsing comes from pydantic-settings). `main.py`: after the router includes, add `CORSMiddleware` with `allow_origins=get_settings().cors_origins`, `allow_credentials=False`, `allow_methods=["*"]`, `allow_headers=["*"]` (spec §7; no cookies, Bearer header only).

- [ ] **Step 4: Run tests to verify they pass**

Run: `..\.venv... -m pytest tests/test_cors.py tests/test_config.py -v`
Expected: PASS, all.

- [ ] **Step 5: Full backend verification**

Run: `ruff check .`; `ruff format --check .`; `mypy app tests`; `pytest` (from `backend/`)
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py app/main.py tests/test_config.py tests/test_cors.py
git commit -m "feat(backend): allow configured CORS origins"
```

---

### Task 2: web/ toolchain, theme, and app shell

**Files:**
- Create: `web/package.json`, `web/tsconfig*.json`, `web/vite.config.ts`, `web/eslint.config.js`, `web/.prettierrc`, `web/.prettierignore`, `web/index.html`, `web/src/main.tsx`, `web/src/app/App.tsx`, `web/src/theme/theme.ts`, `web/src/theme/global.css`, `web/src/test/setup.ts`, `web/src/env.d.ts`, `web/.gitignore`
- Test: `web/src/app/App.test.tsx`, `web/src/theme/theme.test.tsx`
- Delete: create-vite template cruft (`src/App.css`, `src/assets/react.svg`, `public/vite.svg` as needed)

**Interfaces:**
- Consumes: nothing from this plan (first web task).
- Produces: `createAppTheme(): ThemeOptions` in `src/theme/theme.ts` (accent `#5664D2`, `Work Sans` headings, `Inter` body, `borderRadius: 12`); npm scripts `dev`, `build`, `preview`, `lint`, `test`, `e2e`, `format`, `format:check`; `renderWithProviders` arrives in Task 4 (this task's test uses plain `render`); `VITE_API_BASE_URL` env typing in `src/env.d.ts`.

- [ ] **Step 1: Scaffold and install**

Run from repo root: `npm create vite@latest web -- --template react-ts`, then in `web/`: `npm install`, then `npm i @mui/material @emotion/react @emotion/styled @reduxjs/toolkit react-redux react-router @fontsource/inter @fontsource/work-sans`, then `npm i -D tailwindcss @tailwindcss/vite vitest jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom msw prettier @eslint/js eslint typescript-eslint eslint-plugin-react-hooks eslint-plugin-react-refresh @playwright/test`. Prettier: `{ "printWidth": 100 }` (`.prettierrc`), plus `format`/`format:check` scripts. Remove unused template files.

- [ ] **Step 2: Wire the test config**

`vite.config.ts`: plugins `react()` + `tailwindcss()`, and `test: { globals: true, environment: "jsdom", setupFiles: ["./src/test/setup.ts"], exclude: ["e2e/**"] }`. `src/test/setup.ts`: import `@testing-library/jest-dom/vitest` and MSW's server (Task 4 adds handlers; here only `beforeAll(() => server.listen({ onUnhandledRequest: "warn" }))`, `afterEach(() => server.resetHandlers())`, `afterAll(() => server.close())` - server starts with an empty handler list).

- [ ] **Step 3: Write the failing smoke test**

`src/app/App.test.tsx`:

```tsx
it("renders the app shell with the RAG wordmark", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "RAG" })).toBeInTheDocument();
});
```

Run: `npm test` - Expected: FAIL (`App` renders the template counter, not the wordmark).

- [ ] **Step 4: Implement theme and shell**

`src/theme/theme.ts`: `createAppTheme` using `createTheme`-compatible options - `palette.primary.main = "#5664D2"`, `typography.h1..h6.fontFamily = '"Work Sans", "Helvetica", "Arial", sans-serif'`, `typography.fontFamily = '"Inter", "Helvetica", "Arial", sans-serif'`, `shape.borderRadius = 12`. `src/theme/global.css`: `@import "tailwindcss";` plus `@fontsource` weight imports (Inter 400/500, Work Sans 500/600). `src/main.tsx`: import global.css, mount `App`. `App.tsx`: `ThemeProvider` + `CssBaseline` + centered `Typography variant="h1">RAG` placeholder shell. `index.html`: `<title>RAG</title>`, `lang="en"`. `src/env.d.ts`: `ImportMetaEnv { readonly VITE_API_BASE_URL?: string }`. `web/.gitignore`: `node_modules/`, `dist/`, `test-results/`, `playwright-report/`.

- [ ] **Step 5: Verify theme in the test**

`src/theme/theme.test.tsx` (written in Step 3, before the theme exists):

```tsx
it("matches the Devias palette and type stack", () => {
  const theme = createAppTheme();
  expect(theme.palette?.primary?.main).toBe("#5664D2");
  expect(theme.typography?.h1?.fontFamily).toContain('"Work Sans"');
  expect(theme.typography?.fontFamily).toContain('"Inter"');
  expect(theme.shape?.borderRadius).toBe(12);
});
```

Run: `npm test` - Expected: PASS.

- [ ] **Step 6: Lint and build**

Run: `npm run lint`; `npm run format:check`; `npm run build`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add -A web
git commit -m "feat(web): scaffold Vite React app with theme and toolchain"
```

---

### Task 3: Marketing layout and landing page

**Files:**
- Create: `web/src/layouts/MarketingLayout.tsx`, `web/src/features/landing/LandingPage.tsx`
- Test: `web/src/features/landing/LandingPage.test.tsx`

**Interfaces:**
- Consumes: `createAppTheme` (Task 2).
- Produces: `MarketingLayout({ children })` (wordmark + nav slot); `LandingPage` at `/` with CTAs `Get started` -> `/register` and `Sign in` -> `/login`; a three-step strip: `Create a project`, `Upload documents`, `Ask questions`; hero copy exactly: `Your documents, searchable by meaning - upload, ask, get grounded answers`.

- [ ] **Step 1: Write the failing test**

```tsx
it("renders the hero copy and both CTAs with correct hrefs", () => {
  render(<LandingPage />, { wrapper: MemoryRouter });
  expect(screen.getByRole("heading", { name: /searchable by meaning/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/register");
  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
});

it("renders the three how-it-works steps", () => {
  // asserts "Create a project", "Upload documents", "Ask questions" all visible
});
```

Run: `npm test -- LandingPage` - Expected: FAIL (module missing).

- [ ] **Step 2: Implement**

`MarketingLayout`: `Container maxWidth="md"` with the `RAG` wordmark (`Typography`), `Divider`-subtle footer. `LandingPage`: hero (h1 with the exact copy above, supporting sentence), CTA buttons as `Button component="a"` links (contained + outlined), then the three-step strip as a three-column grid (MUI `Grid`/`Stack`), each step a small card (`Card` with 12px radius). Spacious Devias styling; Tailwind utilities allowed.

- [ ] **Step 3: Run tests** - `npm test -- LandingPage` - Expected: PASS.

- [ ] **Step 4: Lint/build** - `npm run lint`, `npm run build` - Expected: green.

- [ ] **Step 5: Commit** - `git commit -m "feat(web): landing page in the Devias style"`

---

### Task 4: Session module - tokenStorage, api client, authSlice, store

**Files:**
- Create: `web/src/lib/tokenStorage.ts`, `web/src/app/api.ts`, `web/src/app/store.ts`, `web/src/app/hooks.ts`, `web/src/features/auth/authSlice.ts`, `web/src/test/handlers.ts`, `web/src/test/server.ts`, `web/src/test/test-utils.tsx`
- Test: `web/src/lib/tokenStorage.test.ts`, `web/src/features/auth/authSlice.test.ts`, `web/src/app/api.test.ts`

**Interfaces:**
- Consumes: `import.meta.env.VITE_API_BASE_URL` (Task 2).
- Produces (all later tasks use these):
  - `loadToken(): string | null`, `saveToken(token: string): void`, `clearToken(): void` (key `"rag.accessToken"`).
  - `API_BASE_URL: string`; `baseQuery` (`fetchBaseQuery` with `prepareHeaders` injecting `Bearer <token>` from `getState().auth.token`); `getErrorMessage(error: unknown): string`; `api = createApi({ reducerPath: "api", baseQuery, tagTypes: ["Project", "Workspace", "Team"], endpoints: () => ({}) })`.
  - `type AuthUser = { id: string; email: string }`; `type AuthState = { token: string | null; user: AuthUser | null; status: "idle" | "booting" | "busy" }`.
  - Thunks: `bootstrapAuth(): AuthUser | null`; `loginUser({ email, password }): AuthUser`; `registerUser({ email, password }): AuthUser`; `logoutUser(): void`. All call `baseQuery(args, { dispatch, getState }, undefined)`; login/register: POST -> `saveToken` -> `GET /users/me` (map `{user_id, email}` -> `AuthUser`); logout: POST `/auth/logout`, ignore its outcome, always `clearToken` locally and dispatch `api.util.resetApiState()` (spec §6.2).
  - `store`, `RootState`, `AppStore`; `useAppDispatch`, `useAppSelector`; `renderWithProviders(ui, { route?, preloadedState? })`.
  - MSW default handlers (in `src/test/handlers.ts`): `POST /auth/register` -> 201 `{access_token: "t-register", token_type: "bearer"}`; `POST /auth/login` -> 200 same with `"t-login"`; `POST /auth/logout` -> 204; `GET /users/me` -> 200 `{user_id: "u-1", email: "user@example.test"}`; `GET /projects` -> 200 `[]`; `GET /workspaces` -> 200 `[{id: "w-1", name: "Default"}]`; `GET /workspaces/w-1/teams` -> 200 `[{id: "t-1", name: "Default", workspace_id: "w-1"}]`.

- [ ] **Step 1: Write the failing tests**

`tokenStorage.test.ts`: save/load roundtrip; load with empty storage -> `null`; clear -> `null`. `api.test.ts` (`getErrorMessage` only, pure): `{status: 409, data: {detail: "email already registered"}}` -> `"email already registered"`; 422-array detail -> `"Check the highlighted fields and try again."`; `{status: "FETCH_ERROR", data: undefined, error: "..."}` -> `"Could not reach the server. Check your connection and try again."`; unknown shape -> `"Something went wrong. Please try again."`.

`authSlice.test.ts` (store via `configureStore`, MSW handlers per case):

```ts
it("login stores the token and hydrates the user", async () => {
  const state = await dispatched(loginUser({ email: "user@example.test", password: "password123" }));
  expect(state.auth.token).toBe("t-login");
  expect(loadToken()).toBe("t-login");
  expect(state.auth.user).toEqual({ id: "u-1", email: "user@example.test" });
});

it("register then 409 rejects without storing", async () => {...});  // override handler -> 409
it("logout posts, clears storage and resets the api cache even when the call fails", async () => {...});  // override -> 500; storage cleared; api reducer state empty
it("bootstrap with no stored token fulfills null", async () => {...});
it("bootstrap with a valid stored token hydrates the user", async () => {...});
it("bootstrap with a revoked stored token clears everything", async () => {...});  // override /users/me -> 401
it("status tracks busy while a login is in flight", async () => {...});  // deferred handler
```

Run: `npm test -- tokenStorage authSlice api.test` - Expected: FAIL (modules missing).

- [ ] **Step 2: Implement**

Per Interfaces above. `tokenStorage.ts` carries the XSS-tradeoff comment (spec §6.1) naming the httpOnly upgrade path. `authSlice`: `initialState` computed from `loadToken()` (`token: loadToken()`, `status: token ? "booting" : "idle"`); `extraReducers` set `user` + `status` on fulfilled/rejected; store middleware concatenates `api.middleware`; `src/test/test-utils.tsx`: `renderWithProviders` wraps `MemoryRouter` (initialEntries from `route`, default `"/"`) + `Provider` + theme. Wire the Task-2 server import to the new `handlers.ts` (`setupServer(...handlers)`).

- [ ] **Step 3: Run tests** - `npm test` (whole suite) - Expected: PASS (landing + shell + new).

- [ ] **Step 4: Lint/build** - Expected: green.

- [ ] **Step 5: Commit** - `git commit -m "feat(web): auth session module (token storage, api client, authSlice)"`

---

### Task 5: Routing, RequireAuth guard, bootstrap wiring

**Files:**
- Create: `web/src/app/AppRoutes.tsx`, `web/src/app/RequireAuth.tsx`, `web/src/app/BootSplash.tsx`, `web/src/features/auth/LoginPage.tsx`, `web/src/features/auth/RegisterPage.tsx`, `web/src/features/projects/ProjectsPage.tsx` (scaffolds)
- Modify: `web/src/app/App.tsx` (Provider + BrowserRouter + AppRoutes + bootstrap effect), `web/src/app/App.test.tsx`
- Test: `web/src/app/RequireAuth.test.tsx`, `web/src/app/App.test.tsx`

**Interfaces:**
- Consumes: `store`, `useAppDispatch/Selector`, `selectAuth` (Task 4); `LandingPage` (Task 3).
- Produces: `RequireAuth({ children })` - `status === "booting"` -> `BootSplash`; no `token` -> `<Navigate to="/login" replace />`; else children. `AppRoutes`: `/` -> `LandingPage`; `/login` -> `LoginPage`; `/register` -> `RegisterPage`; `/projects` -> `RequireAuth` around `ProjectsPage`; `*` -> `<Navigate to="/" replace />`. `App` dispatches `bootstrapAuth()` on mount when a token exists and no user. `selectAuthStatus`, `selectUser`, `selectToken` selectors exported from `authSlice`.

- [ ] **Step 1: Write the failing tests**

`RequireAuth.test.tsx` (via `renderWithProviders` + `Routes`):

```tsx
it("redirects to /login when unauthenticated", () => {...});  // route "/projects" -> ends at /login
it("renders children when authenticated", () => {...});        // preloadedState user+token -> children visible
it("renders the boot splash while booting", () => {...});      // preloaded status "booting" -> "Preparing your workspace" text
```

`App.test.tsx`: with a token in localStorage and MSW `/users/me` -> 200, visiting `/` (public route) renders the landing; visiting `/projects` (guarded, authenticated) renders the `ProjectsPage` scaffold text; with no token, `/projects` redirects to `/login`.

Run: `npm test -- RequireAuth App` - Expected: FAIL (modules missing).

- [ ] **Step 2: Implement**

Per Interfaces. `BootSplash`: centered `CircularProgress` + text `Preparing your workspace`. Pages are one-line scaffolds this task; Tasks 6/7/9 replace them (each scaffold keeps its route path and file name).

- [ ] **Step 3: Run tests** - `npm test` - Expected: PASS.

- [ ] **Step 4: Lint/build** - Expected: green.

- [ ] **Step 5: Commit** - `git commit -m "feat(web): routing with auth guard and token bootstrap"`

---

### Task 6: Login page and AuthLayout

**Files:**
- Create: `web/src/layouts/AuthLayout.tsx`
- Modify: `web/src/features/auth/LoginPage.tsx` (replace scaffold)
- Test: `web/src/features/auth/LoginPage.test.tsx`, `web/src/layouts/AuthLayout.test.tsx`

**Interfaces:**
- Consumes: `loginUser`, `getErrorMessage`, `useAppDispatch/Selector`, `selectUser` (Task 4); `renderWithProviders`; `RequireAuth` routes (Task 5).
- Produces: `AuthLayout({ children })` - centered card, wordmark link `/`; `LoginPage` - labeled `Email`/`Password` `TextField`s, submit `Button` (`Sign in`), register link (`/register`), inline `Alert` for API errors (`role="alert"`), 401 copy exactly `Invalid email or password.`, busy disables submit, authenticated visit redirects to `/projects`.

- [ ] **Step 1: Write the failing tests**

```tsx
it("renders labeled email and password fields with a sign-in button", () => {...});
it("submits credentials and lands on /projects with the token stored", async () => {...});  // userEvent.type + click; expect loadToken() "t-login" + probe route text
it("shows the friendly 401 message", async () => {...});  // override /auth/login -> 401; expect "Invalid email or password."
it("shows a retryable message when the server is unreachable", async () => {...});  // override -> network error; expect getErrorMessage's network copy
it("keeps the submit button disabled while the request is pending", async () => {...});  // deferred handler
it("redirects authenticated visitors to /projects", () => {...});
```

Run: `npm test -- LoginPage AuthLayout` - Expected: FAIL.

- [ ] **Step 2: Implement**

Plain controlled state (`useState`), no form library. On submit: `try { await dispatch(loginUser(values)).unwrap(); } catch (e) { setError(getErrorMessage(e) with 401 override) }`; success renders `<Navigate to="/projects" replace />`. `AuthLayout`: `Container maxWidth="xs"` + `Card`.

- [ ] **Step 3: Run tests** - `npm test` - Expected: PASS.

- [ ] **Step 4: Lint/build** - Expected: green.

- [ ] **Step 5: Commit** - `git commit -m "feat(web): login page"`

---

### Task 7: Register page

**Files:**
- Modify: `web/src/features/auth/RegisterPage.tsx` (replace scaffold)
- Test: `web/src/features/auth/RegisterPage.test.tsx`

**Interfaces:**
- Consumes: `AuthLayout` (Task 6), `registerUser`, `getErrorMessage`, store hooks, `renderWithProviders`, MSW handlers.
- Produces: `RegisterPage` - `Email`, `Password`, `Confirm password` fields; client check: empty fields and `Passwords do not match.`; submit `Create account`; success -> token stored + `/projects`; 409 -> `That email is already registered.` + `Sign in` link to `/login`; 422 -> `getErrorMessage` 422 copy `Check the highlighted fields and try again.`; pending disables submit; link to `/login` (`Already have an account? Sign in`).

- [ ] **Step 1: Write the failing tests**

Cases: labeled fields render; mismatch shows `Passwords do not match.` and does not post; success stores token + lands on `/projects`; 409 -> friendly copy + `/login` link visible; 422 (override `/auth/register` -> 422 array detail) -> friendly validation copy, no raw dump; pending disables `Create account` (deferred handler); authenticated visit redirects to `/projects`.

Run: `npm test -- RegisterPage` - Expected: FAIL.

- [ ] **Step 2: Implement** - same pattern as LoginPage; confirmation field compared client-side before dispatch.

- [ ] **Step 3: Run tests** - `npm test` - Expected: PASS.

- [ ] **Step 4: Lint/build** - Expected: green.

- [ ] **Step 5: Commit** - `git commit -m "feat(web): register page"`

---

### Task 8: Dashboard layout, user menu, sign-out

**Files:**
- Create: `web/src/layouts/DashboardLayout.tsx`, `web/src/features/auth/UserMenu.tsx`
- Test: `web/src/layouts/DashboardLayout.test.tsx`, `web/src/features/auth/UserMenu.test.tsx`

**Interfaces:**
- Consumes: `selectUser`, `logoutUser`, store hooks, MSW.
- Produces: `DashboardLayout({ children })` - topbar with `RAG` wordmark and `UserMenu`; `UserMenu` - `AvatarButton` (initials from user email), menu shows the email (subheader) and a `Sign out` item; sign-out dispatches `logoutUser()`, waits, then renders `<Navigate to="/" replace />`.

- [ ] **Step 1: Write the failing tests**

`UserMenu.test.tsx`:

```tsx
it("shows the signed-in email in the menu", async () => {...});
it("signs out: posts /auth/logout, clears storage, and returns to the landing", async () => {...});  // assert handler called (msw http spy) + loadToken() null + probe text of "/"
it("still signs out when the revocation call fails", async () => {...});  // override /auth/logout -> 500; storage still cleared
```

`DashboardLayout.test.tsx`: renders topbar + children; unauthenticated (no user) renders nothing crashing - the layout is only used inside guarded routes, so the test preloads a user.

Run: `npm test -- UserMenu DashboardLayout` - Expected: FAIL.

- [ ] **Step 2: Implement** - MUI `AppBar`/`Toolbar`, `IconButton` + `Menu` + `MenuItem`; `logoutUser` thunk already handles the best-effort revocation (Task 4); the component only awaits it and navigates.

- [ ] **Step 3: Run tests** - `npm test` - Expected: PASS.

- [ ] **Step 4: Lint/build** - Expected: green.

- [ ] **Step 5: Commit** - `git commit -m "feat(web): dashboard layout with user menu and sign-out"`

---

### Task 9: Projects list page

**Files:**
- Create: `web/src/features/projects/projectsApi.ts`, `web/src/features/projects/ProjectsPage.tsx` (replaces the scaffold content), `web/src/features/projects/EmptyProjects.tsx`
- Modify: `web/src/features/projects/ProjectsPage.tsx` in place (same route as Task 5)
- Test: `web/src/features/projects/ProjectsPage.test.tsx`

**Interfaces:**
- Consumes: `DashboardLayout` (Task 8); `api`, `useAppDispatch/Selector`; `renderWithProviders`; MSW.
- Produces: `projectsApi` - `getProjects: builder.query<Project[], void>` (`providesTags: ["Project"]`) with `useGetProjectsQuery()` hook and `type Project = { id: string; name: string; is_public: boolean; created_at: string }`; `ProjectsPage` - `DashboardLayout` + header (`Projects` + `Create project` button opening the Task-10 dialog), MUI `Table` with columns `Name`, `Visibility`, `Created`; `is_public` maps to `Public`/`Private` `Chip`s; `Created` renders `new Date(created_at).toLocaleDateString()`; `isLoading` -> skeleton rows (`Skeleton` x5); error -> `Snackbar` with `Could not load projects.` + `Try again` (dispatch `api.util.invalidateTags(["Project"])`... or `refetch()`); empty -> `EmptyProjects` card (`No projects yet` + create CTA wired in Task 10).

- [ ] **Step 1: Write the failing tests**

```tsx
it("renders project rows with name, visibility, and created date", async () => {...});  // override GET /projects -> two projects incl. one is_public
it("shows skeletons while loading", async () => {...});  // deferred handler
it("shows the empty state when there are no projects", async () => {...});
it("shows a retryable snackbar when the API is unreachable", async () => {...});  // override -> network error; "Try again" visible
```

Run: `npm test -- ProjectsPage` - Expected: FAIL.

- [ ] **Step 2: Implement** - per Interfaces; the `Create project` button is present but the dialog arrives in Task 10 (keep a `TODO`-free noop: render the button disabled until Task 10 wires it - no, simpler: Task 9 renders the button and Task 10 replaces its `onClick`. The test for the button lives in Task 10).

- [ ] **Step 3: Run tests** - `npm test` - Expected: PASS.

- [ ] **Step 4: Lint/build** - Expected: green.

- [ ] **Step 5: Commit** - `git commit -m "feat(web): projects list page"`

---

### Task 10: Create project dialog with team picker

**Files:**
- Create: `web/src/features/workspaces/workspacesApi.ts` (type `Workspace`, `useGetWorkspacesQuery`), `web/src/features/workspaces/teamsApi.ts` (type `Team`, `useGetWorkspaceTeamsQuery`), `web/src/features/projects/CreateProjectDialog.tsx`
- Modify: `web/src/features/projects/projectsApi.ts` (add `createProject` mutation), `web/src/features/projects/ProjectsPage.tsx` (wire the dialog), `web/src/test/handlers.ts` (projects POST handler)
- Test: `web/src/features/projects/CreateProjectDialog.test.tsx`

**Interfaces:**
- Consumes: `projectsApi.getProjects` (Task 9); `DashboardLayout` route context (Task 5).
- Produces: `createProject: builder.mutation<Project, { name: string; team_id: string }>` (`invalidatesTags: ["Project"]`) with `useCreateProjectMutation`; `CreateProjectDialog({ open, onClose })` - `Name` `TextField`, `Workspace` + `Team` `Select`s auto-preselecting the first option once loaded; submit posts `{name, team_id}`; success closes the dialog and the list refetches via tag invalidation; errors inline in the dialog.

- [ ] **Step 1: Write the failing tests**

```tsx
it("populates workspace and team options and auto-preselects the only pair", async () => {...});  // MSW w-1/Default -> t-1
it("posts { name, team_id } and the new project appears in the list", async () => {...});  // POST handler appends; assert dialog closed + new row (tasks 4-handlers GET /projects override or handler state)
it("keeps Create disabled while the request is pending", async () => {...});  // deferred POST
it("shows an inline error when the team is not found (404)", async () => {...});  // override POST -> 404
it("shows a friendly message on 422", async () => {...});  // override POST -> 422 array detail -> "Check the highlighted fields and try again."
it("cancel closes without posting", () => {...});
it("shows an inline error when the teams fetch fails (404 stale workspace)", async () => {...});  // override teams -> 404
```

Run: `npm test -- CreateProjectDialog` - Expected: FAIL.

- [ ] **Step 2: Implement**

Two chained queries: `useGetWorkspacesQuery()` then `useGetWorkspaceTeamsQuery(selectedWorkspaceId)`; preselect `selectedWorkspaceId`/`teamId` via `useEffect` when data arrives. Submit: `try { await createProject(values).unwrap(); onClose(); } catch (e) { setDialogError(getErrorMessage(e)) }` - the tag invalidation refetches the table.

- [ ] **Step 3: Run tests** - `npm test` - Expected: PASS.

- [ ] **Step 4: Lint/build** - Expected: green.

- [ ] **Step 5: Commit** - `git commit -m "feat(web): create project dialog with team picker"`

---

### Task 11: Playwright E2E, visual check, final verification

**Files:**
- Create: `web/playwright.config.ts`, `web/e2e/scripts/bootstrap_db.py`, `web/e2e/scripts/truncate_db.py`, `web/e2e/journey.spec.ts`, `web/e2e/enforcement.spec.ts`
- Modify: `web/package.json` (no change needed - `e2e` script already exists)
- Test: the E2E suites themselves

**Interfaces:**
- Consumes: the whole app (Tasks 2-10) and the backend on the compose Postgres.
- Produces: a passing `npm run e2e` proving the spec's done-when.

- [ ] **Step 1: Write the DB scripts**

`bootstrap_db.py` (run with the root venv python): resolve `../../backend`, import `app.core.db.make_engine`, DROP DATABASE IF EXISTS `rag_e2e`, CREATE it, then run `alembic upgrade head` against `postgresql+psycopg://rag:rag@localhost:5432/rag_e2e` (same migration bootstrap pattern as `backend/tests/conftest.py`). `truncate_db.py`: connect and `TRUNCATE users, workspaces, teams, team_memberships, projects, project_team_roles, revoked_tokens RESTART IDENTITY CASCADE`.

- [ ] **Step 2: Write the Playwright config and specs**

`playwright.config.ts`: `testDir: "e2e"`, `timeout: 30_000`, `workers: 1`, `fullyParallel: false`, `retries: 0`, `use: { baseURL: "http://localhost:5173" }`, `webServer` entries: uvicorn on 8001 (`..\\..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8001`, cwd `backend`, env `RAG_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag_e2e`) and Vite (`npm run dev -- --port 5173 --strictPort`, env `VITE_API_BASE_URL=http://localhost:8001`). Specs use `test.beforeEach` to run `truncate_db.py`.

`journey.spec.ts`:

```ts
test("register -> default project -> create -> sign out", async ({ page }) => {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2)}@example.test`;
  await page.goto("/register");
  // fill email/password/confirm, submit -> expect URL /projects, row "Default" visible
  // open Create project, pick team (preselected), type "Research notes", Create
  // expect row "Research notes" visible
  const oldToken = await page.evaluate(() => localStorage.getItem("rag.accessToken"));
  // open user menu, click Sign out -> expect URL "/" and landing hero visible
  // replay the revoked token: expect 401
  const response = await request.get("http://localhost:8001/projects", { headers: { authorization: `Bearer ${oldToken}` } });
  expect(response.status()).toBe(401);
});
```

`enforcement.spec.ts`: logged-out `page.goto("/projects")` redirects to `/login`; after login with the just-registered credentials, `/projects` renders.

- [ ] **Step 3: Run the suite**

Run: `npm run e2e` (from `web/`, Postgres up via `docker compose up -d db` in `deploy/` if not running)
Expected: PASS. A failure is a real finding - debug it (`superpowers:systematic-debugging`), do not relax the spec.

- [ ] **Step 4: Manual visual check**

Run both dev servers; check landing, login, register, projects (with rows and empty), and the create dialog at 390px, 768px, and 1280px widths. Fix anything glaring (spacing, alignment, truncation, contrast) and note remaining polish in `docs/backlog.md`.

- [ ] **Step 5: Final whole-system verification**

Run: backend - `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`; web - `npm run lint`, `npm run format:check`, `npm test`, `npm run build`, `npm run e2e`.
Expected: all green.

- [ ] **Step 6: Update the spec status and commit**

`docs/superpowers/specs/2026-10-09-s2-web-ui-foundations-design.md`: Status -> `Implemented on master (S2).` Commit:

```bash
git add web playwright docs/superpowers/specs/2026-10-09-s2-web-ui-foundations-design.md docs/backlog.md
git commit -m "test(e2e): browser journey suite against the real stack"
```