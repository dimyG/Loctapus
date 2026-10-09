import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { saveToken } from "../lib/tokenStorage";
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

  it("renders the landing on the public route for a token holder", async () => {
    saveToken("t-boot");
    renderApp("/");
    expect(
      await screen.findByRole("heading", { name: /searchable by meaning/i }),
    ).toBeInTheDocument();
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
