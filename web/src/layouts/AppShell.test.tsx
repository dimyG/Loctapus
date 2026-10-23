import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { initialRootState } from "../app/store";
import type { Answer } from "../features/chat/answersApi";
import ChatPage from "../features/chat/ChatPage";
import SourcesPage from "../features/sources/SourcesPage";
import type { Upload } from "../features/uploads/uploadsApi";
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

/** A canned answer the chat panel renders once its POST resolves. */
const answerFixture: Answer = {
  answer: "Rotate the garage key from the admin UI. [1]",
  route: "retrieve",
  conversation_id: "conv-1",
  chunks: [],
};

/** A ready source item on p-2, so the switched-to project is chattable. */
const readyUploadP2: Upload = {
  id: "s-9",
  project_id: "p-2",
  status: "ready",
  filename: "paper.pdf",
  created_at: "2026-10-12T10:00:00Z",
};

/**
 * Renders the shell around the real chat and sources routes, so a project
 * switch exercises the same remount wiring the app's layout route uses.
 */
function renderProjectShell(route: string) {
  server.use(http.get("*/projects", () => HttpResponse.json(projectRows)));
  return renderWithProviders(
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/projects/:projectId/chat" element={<ChatPage />} />
        <Route path="/projects/:projectId/sources" element={<SourcesPage />} />
      </Route>
    </Routes>,
    { route, preloadedState: authed() },
  );
}

/** Opens the topbar project select and picks the named project. */
async function switchProject(name: string) {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "Project" }));
  fireEvent.click(await screen.findByRole("option", { name }));
}

describe("AppShell", () => {
  beforeEach(() => {
    // A stored last-project id from an earlier test must not leak between cases.
    window.localStorage.clear();
  });

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

  it("remembers the project the URL carries as the last opened project", () => {
    renderWithProviders(
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/projects/:projectId/sources" element={<div>sources-page</div>} />
        </Route>
      </Routes>,
      { route: "/projects/p-2/sources", preloadedState: authed() },
    );
    // The literal key pins the storage contract; a rename must fail loudly.
    expect(window.localStorage.getItem("rag.lastProjectId")).toBe("p-2");
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

  it("drops the old project's chat thread when the topbar switches projects", async () => {
    server.use(
      http.get("*/api/projects/p-2", () => HttpResponse.json(projectRows[1])),
      http.get("*/api/projects/p-2/uploads", () => HttpResponse.json([readyUploadP2])),
      http.post("*/api/projects/p-1/answer", () => HttpResponse.json(answerFixture)),
    );
    renderProjectShell("/projects/p-1/chat");
    const user = userEvent.setup({ applyAccept: false });
    await user.type(
      await screen.findByLabelText("Ask a question"),
      "How do I rotate the garage key?",
    );
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(answerFixture.answer)).toBeInTheDocument();
    await switchProject("Research");
    // The new project gets a fresh panel: p-2 is chattable, but its thread
    // must hold no trace of p-1's question or answer.
    expect(await screen.findByLabelText("Ask a question")).toHaveValue("");
    expect(screen.queryByText("How do I rotate the garage key?")).not.toBeInTheDocument();
    expect(screen.queryByText(answerFixture.answer)).not.toBeInTheDocument();
  });

  it("drops the old project's source rows when the topbar switches projects", async () => {
    server.use(
      http.get("*/api/projects/p-2", () => HttpResponse.json(projectRows[1])),
      http.get("*/api/projects/p-2/uploads", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderProjectShell("/projects/p-1/sources");
    expect(await screen.findByText("brief.pdf")).toBeInTheDocument();
    expect(screen.getByText("report.docx")).toBeInTheDocument();
    await switchProject("Research");
    // p-2's uploads fetch fails with nothing cached: the error card must
    // show, and p-1's rows must not survive the switch.
    expect(await screen.findByText("Could not load the source items.")).toBeInTheDocument();
    expect(screen.queryByText("brief.pdf")).not.toBeInTheDocument();
    expect(screen.queryByText("report.docx")).not.toBeInTheDocument();
    expect(screen.queryByText("broken.pdf")).not.toBeInTheDocument();
  });
});
