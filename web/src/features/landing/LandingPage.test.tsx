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

  it("renders the hero copy with one centered CTA", () => {
    renderLanding();
    expect(
      screen.getByRole("heading", { name: "Loctapus Bring your knowledge base to life" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Combine knowledge from multiple sources into a unified, searchable knowledge base and make it accessible to applications, AI agents, and users through web chat, APIs, and MCP.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Under development")).toBeVisible();
    // The navbar and the hero both render "Get started", but "Sign in" leaves
    // the hero and survives only in the navbar (spec decision 7).
    const started = screen.getAllByRole("link", { name: "Get started" });
    expect(started).toHaveLength(2);
    for (const link of started) {
      expect(link).toHaveAttribute("href", "/register");
    }
    const signIn = screen.getAllByRole("link", { name: "Sign in" });
    expect(signIn).toHaveLength(1);
    expect(signIn[0]).toHaveAttribute("href", "/login");
  });

  it("renders the three how-it-works steps with their upcoming tags", () => {
    renderLanding();
    for (const step of ["Connect your sources", "Loctapus organizes it", "Make it available"]) {
      expect(screen.getByRole("heading", { name: step })).toBeVisible();
    }
    expect(screen.getByText("PDF & DOCX")).toBeVisible();
    expect(screen.getByText("Web chat")).toBeVisible();
    for (const tag of ["Google Drive", "Websites", "API", "MCP"]) {
      expect(screen.getByText(`${tag} · Coming soon`)).toBeVisible();
    }
  });

  it("renders the four team cards", () => {
    renderLanding();
    expect(screen.getByRole("heading", { name: "Built for teams" })).toBeVisible();
    for (const title of [
      "Organized the way you work",
      "Access only where it's granted",
      "Meet your customers where they are",
      "Always in sync, fully managed",
    ]) {
      expect(screen.getByRole("heading", { name: title })).toBeVisible();
    }
  });

  it("renders both use cases", () => {
    renderLanding();
    expect(screen.getByRole("heading", { name: "Use cases" })).toBeVisible();
    for (const title of [
      "Self-service support on your docs site",
      "Hundreds of PDFs, ready for your agents",
    ]) {
      expect(screen.getByRole("heading", { name: title })).toBeVisible();
    }
    // Two team cards and both use cases are upcoming, one chip each.
    expect(screen.getAllByText("Coming soon")).toHaveLength(4);
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
    expect(
      screen.getByRole("heading", { name: "Loctapus Bring your knowledge base to life" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("navigates to register through the router", async () => {
    renderLanding();
    const [getStarted] = screen.getAllByRole("link", { name: "Get started" });
    await userEvent.setup().click(getStarted);
    expect(await screen.findByRole("heading", { name: "Create account" })).toBeInTheDocument();
  });

  it("navigates to login through the router", async () => {
    renderLanding();
    // The hero no longer repeats "Sign in"; the navbar's single link remains.
    await userEvent.setup().click(screen.getByRole("link", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});
