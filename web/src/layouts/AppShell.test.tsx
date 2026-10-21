import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { initialRootState } from "../app/store";
import { server } from "../test/server";
import { renderWithProviders } from "../test/test-utils";
import AppShell from "./AppShell";

/** Signed-in state; the account button only renders with a session user. */
const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

const projectRows = [
  { id: "p-1", name: "Default", is_public: false, created_at: "2026-10-09T10:00:00Z" },
  { id: "p-2", name: "Research", is_public: true, created_at: "2026-10-10T11:00:00Z" },
];

/** Renders the shell around a stubbed sources route, the way the guarded layout route nests it. */
function renderShell() {
  server.use(http.get("*/projects", () => HttpResponse.json(projectRows)));
  return renderWithProviders(
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/projects" element={<div>projects-page</div>} />
        <Route path="/projects/p-1/sources" element={<div>sources-page</div>} />
      </Route>
    </Routes>,
    { route: "/projects/p-1/sources", preloadedState: authed() },
  );
}

describe("AppShell", () => {
  it("renders the sidebar, the topbar controls, and the routed page", async () => {
    renderShell();
    // jsdom does not evaluate the media-query CSS the drawer's responsive
    // display generates, so the permanent sidebar's items answer role
    // queries either way; the hidden-inclusive query also reaches them.
    expect(screen.getByRole("link", { name: "Sources", hidden: true })).toHaveAttribute(
      "href",
      "/projects/p-1/sources",
    );
    expect(screen.getByRole("button", { name: "menu" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Project" })).toBeInTheDocument();
    // The mode switcher appears once useColorScheme settles its mount effect.
    expect(await screen.findByRole("button", { name: "color mode" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "account menu" })).toBeInTheDocument();
    expect(screen.getByText("sources-page")).toBeInTheDocument();
  });

  it("opens the mobile drawer from the hamburger and closes it on navigation", async () => {
    renderShell();
    const user = userEvent.setup();
    // Both drawers render the same nav, and hidden-inclusive queries see
    // every copy, so the count tells how many drawers are in the tree.
    expect(screen.getAllByRole("link", { name: "Chat", hidden: true })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "menu" }));
    expect(screen.getAllByRole("link", { name: "Chat", hidden: true })).toHaveLength(2);
    // The temporary drawer mounts its portal at the end of the body, so its
    // link is the last one; picking a destination navigates and closes it.
    const drawerLinks = screen.getAllByRole("link", { name: "Projects", hidden: true });
    await user.click(drawerLinks[drawerLinks.length - 1]);
    expect(await screen.findByText("projects-page")).toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.getAllByRole("link", { name: "Chat", hidden: true })).toHaveLength(1);
      },
      { timeout: 3000 },
    );
  });
});
