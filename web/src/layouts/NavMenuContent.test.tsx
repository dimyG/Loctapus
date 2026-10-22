import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { initialRootState } from "../app/store";
import { server } from "../test/server";
import { renderWithProviders } from "../test/test-utils";
import NavMenuContent from "./NavMenuContent";

/** Signed-in state; the nav renders behind the auth guard in the real app. */
const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

// Oldest first on purpose: the newest-first ordering must come from the code,
// not from the fixture. p-2 is the latest project.
const projectRows = [
  { id: "p-1", name: "Default", is_public: false, created_at: "2026-10-09T10:00:00Z" },
  { id: "p-2", name: "Research", is_public: true, created_at: "2026-10-10T11:00:00Z" },
];

/** Renders the nav directly at the given route; the list carries no responsive hiding. */
function renderNav(route: string) {
  server.use(http.get("*/projects", () => HttpResponse.json(projectRows)));
  return renderWithProviders(<NavMenuContent />, { route, preloadedState: authed() });
}

describe("NavMenuContent", () => {
  beforeEach(() => {
    // A stored last-project id from an earlier test must not leak between cases.
    window.localStorage.clear();
  });

  it("renders all five sections", () => {
    renderNav("/projects/p-1/sources");
    for (const label of ["Projects", "Sources", "Chat", "Users", "Analytics"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("disables the future sections with Coming soon chips", () => {
    renderNav("/projects/p-1/sources");
    // MUI exposes disabled list items via aria-disabled, not the native attribute.
    expect(screen.getByRole("button", { name: /users/i })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: /analytics/i })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getAllByText("Coming soon")).toHaveLength(2);
  });

  it("marks the sources item current on /projects/p-1/sources", () => {
    renderNav("/projects/p-1/sources");
    expect(screen.getByRole("link", { name: "Sources" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Projects" })).not.toHaveAttribute("aria-current");
  });

  it("marks only sources current below the sources section", () => {
    renderNav("/projects/p-2/sources/upload");
    expect(screen.getByRole("link", { name: "Sources" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Projects" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Chat" })).not.toHaveAttribute("aria-current");
  });

  it("links sources and chat to the latest project from /projects", async () => {
    renderNav("/projects");
    // The links only exist once the project list resolves.
    expect(await screen.findByRole("link", { name: "Sources" })).toHaveAttribute(
      "href",
      "/projects/p-2/sources",
    );
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute(
      "href",
      "/projects/p-2/chat",
    );
  });

  it("links sources and chat to the remembered project from /projects", async () => {
    // The literal key pins the storage contract; a rename must fail loudly.
    window.localStorage.setItem("rag.lastProjectId", "p-1");
    renderNav("/projects");
    expect(await screen.findByRole("link", { name: "Sources" })).toHaveAttribute(
      "href",
      "/projects/p-1/sources",
    );
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute(
      "href",
      "/projects/p-1/chat",
    );
  });

  it("falls back to the newest project when the remembered one is not in the list", async () => {
    // A deleted project or another user's id on the same browser must not
    // produce links to a project the list does not hold.
    window.localStorage.setItem("rag.lastProjectId", "p-gone");
    renderNav("/projects");
    expect(await screen.findByRole("link", { name: "Sources" })).toHaveAttribute(
      "href",
      "/projects/p-2/sources",
    );
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute(
      "href",
      "/projects/p-2/chat",
    );
  });

  it("disables sources and chat when there are no projects", () => {
    // The baseline projects handler returns []; sources and chat have no
    // target without a project, in the loading state and the empty one alike.
    renderWithProviders(<NavMenuContent />, { route: "/projects", preloadedState: authed() });
    expect(screen.getByRole("button", { name: "Sources" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("button", { name: "Chat" })).toHaveAttribute("aria-disabled", "true");
  });
});
