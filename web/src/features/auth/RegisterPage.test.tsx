import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router";
import { initialRootState } from "../../app/store";
import { loadToken } from "../../lib/tokenStorage";
import { renderWithProviders } from "../../test/test-utils";
import { server } from "../../test/server";
import ChatLanding from "../chat/ChatLanding";
import ChatPage from "../chat/ChatPage";
import ProjectsPage from "../projects/ProjectsPage";
import RegisterPage from "./RegisterPage";

/** The funnel's target project: chattable through the baseline ready upload. */
const projectP1 = {
  id: "p-1",
  name: "Default",
  is_public: false,
  created_at: "2026-10-09T10:00:00Z",
};

/** Makes the projects list land the funnel on p-1's chat. */
function chattableProjectP1() {
  server.use(http.get("*/api/projects", () => HttpResponse.json([projectP1])));
}

/** Renders RegisterPage behind the routes it navigates within. */
function renderRegister(preloadedState = initialRootState()) {
  return renderWithProviders(
    <Routes>
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/app" element={<ChatLanding />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/projects/:projectId/chat" element={<ChatPage />} />
      <Route path="/login" element={<div>login-page</div>} />
    </Routes>,
    { route: "/register", preloadedState },
  );
}

type Form = { email?: string; password?: string; confirm?: string };

async function fillForm(
  user: ReturnType<typeof userEvent.setup>,
  { email = "user@example.test", password = "password123", confirm = "password123" }: Form = {},
) {
  await user.type(screen.getByLabelText(/Email/), email);
  await user.type(screen.getByLabelText(/^Password/), password);
  await user.type(screen.getByLabelText(/Confirm password/), confirm);
}

function trackRegistrations() {
  const requests: unknown[] = [];
  server.use(
    http.post("*/auth/register", ({ request }) => {
      requests.push(request);
      return HttpResponse.json(
        { access_token: "t-register", token_type: "bearer" },
        { status: 201 },
      );
    }),
  );
  return requests;
}

describe("RegisterPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders labeled email, password, and confirmation fields", () => {
    renderRegister();
    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Confirm password/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create account" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("shows Passwords do not match. and does not post on mismatch", async () => {
    const requests = trackRegistrations();
    renderRegister();
    const user = userEvent.setup();
    await fillForm(user, { confirm: "different" });
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(requests).toHaveLength(0);
    expect(loadToken()).toBeNull();
  });

  it("shows a required-fields message and does not post when empty", async () => {
    const requests = trackRegistrations();
    renderRegister();
    await userEvent.setup().click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("All fields are required.");
    expect(requests).toHaveLength(0);
  });

  it("shows a length hint when the password is under 8 characters", async () => {
    const requests = trackRegistrations();
    renderRegister();
    const user = userEvent.setup();
    await fillForm(user, { password: "short", confirm: "short" });
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Password must be at least 8 characters.",
    );
    expect(requests).toHaveLength(0);
  });

  it("stores the token and lands on the latest chattable project's chat", async () => {
    chattableProjectP1();
    renderRegister();
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(loadToken()).toBe("t-register");
    // The resolver walks p-1 (ready report.docx in the baseline uploads).
    expect(await screen.findByLabelText("Ask a question")).toBeInTheDocument();
  });

  it("shows the friendly 409 copy with a sign-in link", async () => {
    server.use(
      http.post("*/auth/register", () =>
        HttpResponse.json({ detail: "email already registered" }, { status: 409 }),
      ),
    );
    renderRegister();
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("That email is already registered.");
    expect(within(alert).getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("shows the friendly 422 message without a raw dump", async () => {
    server.use(
      http.post("*/auth/register", () =>
        HttpResponse.json(
          { detail: [{ loc: ["body", "password"], msg: "string too short" }] },
          { status: 422 },
        ),
      ),
    );
    renderRegister();
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Check the highlighted fields and try again.");
    expect(alert).not.toHaveTextContent("too short");
  });

  it("keeps Create account disabled while the request is pending", async () => {
    chattableProjectP1();
    let resolveRequest: (() => void) | undefined;
    server.use(
      http.post("*/auth/register", async () => {
        await new Promise<void>((resolve) => {
          resolveRequest = resolve;
        });
        return HttpResponse.json(
          { access_token: "t-register", token_type: "bearer" },
          { status: 201 },
        );
      }),
    );
    renderRegister();
    const user = userEvent.setup();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByRole("button", { name: "Create account" })).toBeDisabled();
    await vi.waitFor(() => {
      expect(resolveRequest).toBeDefined();
    });
    resolveRequest?.();
    // On success the form unmounts and the app lands on p-1's chat.
    expect(await screen.findByLabelText("Ask a question")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create account" })).not.toBeInTheDocument();
  });

  it("redirects authenticated visitors to the latest chattable project's chat", async () => {
    chattableProjectP1();
    renderRegister({
      ...initialRootState(),
      auth: {
        token: "t-1",
        user: { id: "u-1", email: "user@example.test" },
        status: "idle",
      },
    });
    expect(await screen.findByLabelText("Ask a question")).toBeInTheDocument();
  });
});
