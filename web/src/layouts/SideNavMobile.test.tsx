import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { initialRootState } from "../app/store";
import { server } from "../test/server";
import { renderWithProviders } from "../test/test-utils";
import SideNavMobile from "./SideNavMobile";

/** Signed-in state; the drawer renders behind the auth guard in the real app. */
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

/** Renders the open drawer beside stub routes, so a navigation lands as visible text. */
function renderDrawer(onClose: () => void) {
  server.use(http.get("*/projects", () => HttpResponse.json(projectRows)));
  return renderWithProviders(
    <>
      <SideNavMobile open onClose={onClose} />
      <Routes>
        <Route path="/projects/p-1/sources" element={<div>sources-page</div>} />
        <Route path="/projects" element={<div>projects-page</div>} />
      </Routes>
    </>,
    { route: "/projects/p-1/sources", preloadedState: authed() },
  );
}

describe("SideNavMobile", () => {
  it("shows the nav items when open", () => {
    renderDrawer(vi.fn());
    for (const label of ["Projects", "Sources", "Chat", "Users", "Analytics"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("closes and navigates when an item is clicked", async () => {
    const onClose = vi.fn();
    renderDrawer(onClose);
    await userEvent.setup().click(screen.getByRole("link", { name: "Projects" }));
    expect(onClose).toHaveBeenCalled();
    expect(await screen.findByText("projects-page")).toBeInTheDocument();
  });
});
