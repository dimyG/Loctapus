import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { initialRootState } from "../../app/store";
import { renderWithProviders } from "../../test/test-utils";
import ChatLanding from "../chat/ChatLanding";
import LoginPage from "../auth/LoginPage";
import RegisterPage from "../auth/RegisterPage";
import ProjectsPage from "../projects/ProjectsPage";
import LandingPage from "./LandingPage";

/** Builds the authed preloaded state the redirect tests seed. */
function authedState(status: "idle" | "busy" = "idle") {
  return {
    ...initialRootState(),
    auth: {
      // The reachable mid-sign-out window keeps the stale token alongside
      // the still-hydrated user; only sessionCleared clears both.
      token: "t-1",
      user: { id: "u-1", email: "user@example.test" },
      status,
    },
  };
}

/** Renders the landing page at "/" behind the routes it links and redirects within. */
function renderLanding(preloadedState = initialRootState()) {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/app" element={<ChatLanding />} />
      <Route path="/projects" element={<ProjectsPage />} />
    </Routes>,
    { route: "/", preloadedState },
  );
}

describe("LandingPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the hero copy and both CTAs with correct hrefs", () => {
    renderLanding();
    expect(screen.getByRole("heading", { name: /searchable by meaning/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("renders the three how-it-works steps", () => {
    renderLanding();
    for (const step of ["Create a project", "Upload documents", "Ask questions"]) {
      expect(screen.getByText(step)).toBeVisible();
    }
  });

  it("redirects authenticated visitors", async () => {
    renderLanding(authedState());
    // The resolver now needs MSW round-trips; with the baseline empty
    // projects list it resolves to /projects.
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  });

  it("renders the landing for a busy session instead of redirecting", () => {
    // Sign-out clears the session while the router lands on "/"; a render
    // can still see the stale user mid-transition. Redirecting then would
    // land the user on the guarded /app, which bounces to /login
    // once the session clears - the race RequireAuth's splash prevents.
    renderLanding(authedState("busy"));
    expect(screen.getByRole("heading", { name: /searchable by meaning/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("navigates to register through the router", async () => {
    renderLanding();
    await userEvent.setup().click(screen.getByRole("link", { name: "Get started" }));
    expect(await screen.findByRole("heading", { name: "Create account" })).toBeInTheDocument();
  });

  it("navigates to login through the router", async () => {
    renderLanding();
    await userEvent.setup().click(screen.getByRole("link", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});
