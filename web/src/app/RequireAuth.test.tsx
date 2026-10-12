import { Route, Routes } from "react-router";
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { initialRootState } from "./store";
import { renderWithProviders } from "../test/test-utils";
import RequireAuth from "./RequireAuth";

function renderGuarded(preloadedState = initialRootState()) {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<div>landing-page</div>} />
      <Route path="/login" element={<div>login-page</div>} />
      <Route
        path="/projects"
        element={
          <RequireAuth>
            <div>projects-page</div>
          </RequireAuth>
        }
      />
    </Routes>,
    { route: "/projects", preloadedState },
  );
}

describe("RequireAuth", () => {
  it("redirects to /login when unauthenticated", () => {
    renderGuarded();
    expect(screen.getByText("login-page")).toBeInTheDocument();
    expect(screen.queryByText("projects-page")).not.toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    renderGuarded({
      ...initialRootState(),
      auth: { token: "t-1", user: { id: "u-1", email: "user@example.test" }, status: "idle" },
    });
    expect(screen.getByText("projects-page")).toBeInTheDocument();
  });

  it("renders the boot splash while booting", () => {
    renderGuarded({
      ...initialRootState(),
      auth: { token: "t-1", user: null, status: "booting" },
    });
    expect(screen.getByText("Preparing your workspace")).toBeInTheDocument();
    expect(screen.queryByText("projects-page")).not.toBeInTheDocument();
  });

  it("renders the splash while an auth transition is in flight", () => {
    // Sign-out clears the session synchronously while the guard is mounted;
    // busy must render the splash so the sign-out navigation lands on "/",
    // never on the guard's /login bounce.
    renderGuarded({
      ...initialRootState(),
      auth: { token: "t-1", user: null, status: "busy" },
    });
    expect(screen.getByText("Preparing your workspace")).toBeInTheDocument();
    expect(screen.queryByText("projects-page")).not.toBeInTheDocument();
  });

  it("sends a signed-out session to the public landing, never to /login", () => {
    // After a completed sign-out the session is "signedout", not "idle":
    // idle + no token means the session expired and must re-authenticate,
    // while signedout means the sign-out flow owns routing and its target
    // is the landing page. Bouncing here reopens the sign-out race.
    renderGuarded({
      ...initialRootState(),
      auth: { token: null, user: null, status: "signedout" },
    });
    expect(screen.getByText("landing-page")).toBeInTheDocument();
    expect(screen.queryByText("login-page")).not.toBeInTheDocument();
  });
});
