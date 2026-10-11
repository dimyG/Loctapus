import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { saveToken } from "../lib/tokenStorage";
import { server } from "../test/server";
import App from "./App";

function renderApp(route: string) {
  window.history.pushState({}, "", route);
  render(<App />);
}

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.pushState({}, "", "/");
  });

  it("redirects a token holder from / to the projects page", async () => {
    saveToken("t-boot");
    renderApp("/");
    // The longest wait in the suite: bootstrap fetch, hydration, redirect,
    // and the guarded render all land inside one findBy. The default 1s
    // budget flakes when parallel files saturate the worker, so allow 5s.
    expect(
      await screen.findByRole("heading", { name: "Projects" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/projects");
  });

  it("renders the about page for public visitors", async () => {
    renderApp("/about");
    expect(await screen.findByRole("heading", { name: "About RAG" })).toBeInTheDocument();
  });

  it("keeps a visitor whose stored token was rejected on the landing", async () => {
    saveToken("t-stale");
    server.use(http.get("*/users/me", () => HttpResponse.json({}, { status: 401 })));
    renderApp("/");
    // The redirect waits for the hydrated user, so a stale token never
    // bounces a public visitor into the guarded login flow.
    expect(
      await screen.findByRole("heading", { name: /searchable by meaning/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("renders the guarded projects page for an authenticated visitor", async () => {
    saveToken("t-boot");
    renderApp("/projects");
    // The page is a scaffold until Task 9 replaces its content.
    expect(await screen.findByText("Projects")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/projects");
  });

  it("redirects unauthenticated visitors from /projects to /login", async () => {
    renderApp("/projects");
    // The login form's email field only renders after the redirect completes.
    expect(await screen.findByLabelText(/Email/)).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
  });
});
