import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { initialRootState } from "../../app/store";
import { loadToken } from "../../lib/tokenStorage";
import { renderWithProviders } from "../../test/test-utils";
import { server } from "../../test/server";
import LoginPage from "./LoginPage";
import ProjectsPage from "../projects/ProjectsPage";
import { Route, Routes } from "react-router";

/** Renders LoginPage behind the routes it navigates within. */
function renderLogin(preloadedState = initialRootState()) {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/projects" element={<ProjectsPage />} />
    </Routes>,
    { route: "/login", preloadedState },
  );
}

async function signIn(
  user: ReturnType<typeof userEvent.setup>,
  email = "user@example.test",
  password = "password123",
) {
  await user.type(screen.getByLabelText(/Email/), email);
  await user.type(screen.getByLabelText(/Password/), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("shows a required-fields message and does not post when empty", async () => {
    const posts: unknown[] = [];
    server.use(
      http.post("*/auth/login", ({ request }) => {
        posts.push(request);
        return HttpResponse.json({ access_token: "t-login", token_type: "bearer" });
      }),
    );
    renderLogin();
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("All fields are required.");
    expect(posts).toHaveLength(0);
  });

  it("renders labeled email and password fields with a sign-in button", () => {
    renderLogin();
    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
    expect(screen.getByRole("link", { name: /create/i })).toHaveAttribute("href", "/register");
  });

  it("submits credentials and lands on /projects with the token stored", async () => {
    renderLogin();
    await signIn(userEvent.setup());
    expect(loadToken()).toBe("t-login");
    expect(await screen.findByText("Projects")).toBeInTheDocument();
  });

  it("shows the friendly 401 message", async () => {
    server.use(
      http.post("*/auth/login", () =>
        HttpResponse.json({ detail: "Not authenticated" }, { status: 401 }),
      ),
    );
    renderLogin();
    await signIn(userEvent.setup());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Invalid email or password.");
  });

  it("shows a retryable message when the server is unreachable", async () => {
    server.use(http.post("*/auth/login", () => HttpResponse.error()));
    renderLogin();
    await signIn(userEvent.setup());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Could not reach the server. Check your connection and try again.",
    );
  });

  it("keeps the submit button disabled while the request is pending", async () => {
    let resolveRequest: (() => void) | undefined;
    server.use(
      http.post("*/auth/login", async () => {
        await new Promise<void>((resolve) => {
          resolveRequest = resolve;
        });
        return HttpResponse.json({ access_token: "t-login", token_type: "bearer" });
      }),
    );
    renderLogin();
    const user = userEvent.setup();
    await signIn(user);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
    await vi.waitFor(() => {
      expect(resolveRequest).toBeDefined();
    });
    resolveRequest?.();
    // On success the form unmounts and the app lands on /projects.
    expect(await screen.findByText("Projects")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("redirects authenticated visitors to /projects", () => {
    renderLogin({
      ...initialRootState(),
      auth: {
        token: "t-1",
        user: { id: "u-1", email: "user@example.test" },
        status: "idle",
      },
    });
    expect(screen.getByText("Projects")).toBeInTheDocument();
  });
});
