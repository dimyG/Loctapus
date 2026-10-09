import { Route, Routes } from "react-router";
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { initialRootState } from "./store";
import { renderWithProviders } from "../test/test-utils";
import RequireAuth from "./RequireAuth";

function renderGuarded(preloadedState = initialRootState()) {
  return renderWithProviders(
    <Routes>
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
});
