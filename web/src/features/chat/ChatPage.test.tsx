import { act, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { initialRootState } from "../../app/store";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import type { Upload } from "../uploads/uploadsApi";
import ChatPage from "./ChatPage";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

/** Renders the page inside its route so useParams carries the project id. */
function renderChat() {
  return renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId/chat" element={<ChatPage />} />
    </Routes>,
    { preloadedState: authed(), route: "/projects/p-1/chat" },
  );
}

const queuedUpload: Upload = {
  id: "s-1",
  project_id: "p-1",
  status: "queued",
  filename: "brief.pdf",
  created_at: "2026-10-12T10:00:00Z",
};
const readyUpload: Upload = {
  ...queuedUpload,
  id: "s-2",
  status: "ready",
  filename: "report.docx",
  created_at: "2026-10-11T10:00:00Z",
};

/** Advances fake timers inside act so store updates and effects flush. */
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("ChatPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the panel when a source item is ready", async () => {
    renderChat();
    // The baseline uploads include a ready row, so the chat input renders.
    expect(await screen.findByLabelText("Ask a question")).toBeInTheDocument();
  });

  it("shows a loading state, not the empty state, while the uploads load", async () => {
    let resolveUploads!: (response: Response) => void;
    server.use(
      http.get(
        "*/projects/p-1/uploads",
        () =>
          new Promise<Response>((resolve) => {
            resolveUploads = resolve;
          }),
      ),
    );
    renderChat();
    // A chattable project must not flash its empty state while the list is in flight.
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.queryByText("Upload sources to start asking questions.")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Ask a question")).not.toBeInTheDocument();
    // The handler only runs once the fetch reaches MSW, so wait for it to fire.
    await waitFor(() => {
      expect(resolveUploads).toBeDefined();
    });
    resolveUploads(HttpResponse.json([queuedUpload, readyUpload]));
    expect(await screen.findByLabelText("Ask a question")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("shows the retryable error state when the uploads list cannot load", async () => {
    server.use(
      http.get("*/projects/p-1/uploads", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderChat();
    expect(await screen.findByText("Could not load the source items.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    // The failure must not read as an empty project: no empty-state copy, no panel.
    expect(screen.queryByText("Upload sources to start asking questions.")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Ask a question")).not.toBeInTheDocument();
  });

  it("shows the empty state until a source item is ready", async () => {
    server.use(http.get("*/projects/p-1/uploads", () => HttpResponse.json([queuedUpload])));
    renderChat();
    expect(
      await screen.findByText("Upload sources to start asking questions."),
    ).toBeInTheDocument();
    // The way out is an absolute project-scoped URL, never a bare /sources.
    expect(screen.getByRole("link", { name: "Go to sources" })).toHaveAttribute(
      "href",
      "/projects/p-1/sources",
    );
    expect(screen.queryByLabelText("Ask a question")).not.toBeInTheDocument();
  });

  it("flips from the empty state to the panel when an upload turns ready", async () => {
    let ready = false;
    let gets = 0;
    server.use(
      http.get("*/projects/p-1/uploads", () => {
        gets += 1;
        return HttpResponse.json(ready ? [readyUpload, queuedUpload] : [queuedUpload]);
      }),
    );
    vi.useFakeTimers();
    try {
      renderChat();
      await advance(0);
      expect(gets).toBe(1);
      await advance(500);
      // The queued-only list settles into the empty state first.
      expect(screen.getByText("Upload sources to start asking questions.")).toBeInTheDocument();
      ready = true;
      await advance(2000);
      expect(gets).toBe(2);
      // The ready row flips the panel on.
      expect(screen.getByLabelText("Ask a question")).toBeInTheDocument();
      expect(
        screen.queryByText("Upload sources to start asking questions."),
      ).not.toBeInTheDocument();
      // A queued row remains, so the poll keeps running while the panel shows.
      await advance(2000);
      expect(gets).toBe(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the not-found state when the project does not exist", async () => {
    server.use(
      http.get("*/projects/p-1", () =>
        HttpResponse.json({ detail: "project not found" }, { status: 404 }),
      ),
    );
    renderChat();
    expect(await screen.findByText("Project not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to projects" })).toBeInTheDocument();
  });
});
