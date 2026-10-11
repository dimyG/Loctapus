import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { initialRootState } from "../../app/store";
import { renderWithProviders } from "../../test/test-utils";
import LoginPage from "../auth/LoginPage";
import RegisterPage from "../auth/RegisterPage";
import ProjectsPage from "../projects/ProjectsPage";
import LandingPage from "./LandingPage";

/** Renders the landing page at "/" behind the routes it links and redirects within. */
function renderLanding(preloadedState = initialRootState()) {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
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

  it("redirects authenticated visitors to the projects page", () => {
    renderLanding({
      ...initialRootState(),
      auth: {
        token: "t-1",
        user: { id: "u-1", email: "user@example.test" },
        status: "idle",
      },
    });
    expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
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
