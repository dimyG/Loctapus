import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router";
import { initialRootState } from "../../app/store";
import RequireAuth from "../../app/RequireAuth";
import { loadToken, saveToken } from "../../lib/tokenStorage";
import { renderWithProviders } from "../../test/test-utils";
import { server } from "../../test/server";
import UserMenu from "./UserMenu";
import LandingPage from "../landing/LandingPage";

/** A seeded authenticated state; the menu only renders for signed-in users. */
const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

// The menu renders BEHIND the guard, the way the app mounts it: sign-out must
// land on the public landing, never on the guard's login bounce.
function renderMenu() {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<div>login-page</div>} />
      <Route
        path="/projects"
        element={
          <RequireAuth>
            <UserMenu />
          </RequireAuth>
        }
      />
    </Routes>,
    { route: "/projects", preloadedState: authed() },
  );
}

async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /account menu/i }));
}

describe("UserMenu", () => {
  beforeEach(() => {
    window.localStorage.clear();
    saveToken("t-1");
  });

  it("shows the signed-in email in the menu", async () => {
    renderMenu();
    await openMenu(userEvent.setup());
    expect(screen.getByText("user@example.test")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();
  });

  it("signs out: posts /auth/logout, clears storage, and returns to the landing", async () => {
    const logoutCalls: unknown[] = [];
    server.use(
      http.post("*/auth/logout", ({ request }) => {
        logoutCalls.push(request);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderMenu();
    const user = userEvent.setup();
    await openMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    // The session clears during the click handler; the landing renders with
    // no user, so the authed-visitor redirect never fires mid-sign-out.
    expect(
      await screen.findByRole("heading", { name: /searchable by meaning/i }),
    ).toBeInTheDocument();
    // And the guard never bounced the sign-out to the login page.
    expect(screen.queryByText("login-page")).not.toBeInTheDocument();
    await vi.waitFor(() => {
      expect(loadToken()).toBeNull();
    });
    expect(logoutCalls).toHaveLength(1);
  });

  it("still signs out when the revocation call fails", async () => {
    server.use(
      http.post("*/auth/logout", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
    );
    renderMenu();
    const user = userEvent.setup();
    await openMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(
      await screen.findByRole("heading", { name: /searchable by meaning/i }),
    ).toBeInTheDocument();
    await vi.waitFor(() => {
      expect(loadToken()).toBeNull();
    });
  });
});
