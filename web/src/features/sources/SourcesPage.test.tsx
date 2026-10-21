import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { initialRootState } from "../../app/store";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import type { Upload } from "../uploads/uploadsApi";
import SourcesPage from "./SourcesPage";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

/** Renders the page inside its route so useParams carries the project id. */
function renderSources() {
  return renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId/sources" element={<SourcesPage />} />
    </Routes>,
    { preloadedState: authed(), route: "/projects/p-1/sources" },
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
const failedUpload: Upload = {
  ...queuedUpload,
  id: "s-3",
  status: "failed",
  filename: "broken.pdf",
  created_at: "2026-10-10T10:00:00Z",
};

/** Advances fake timers inside act so store updates and effects flush. */
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("SourcesPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the toolbar and the fixture rows", async () => {
    renderSources();
    expect(await screen.findByRole("heading", { name: "Sources" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search sources")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add source" })).toBeInTheDocument();
    expect(screen.getByText("brief.pdf")).toBeInTheDocument();
    expect(screen.getByText("report.docx")).toBeInTheDocument();
    expect(screen.getByText("broken.pdf")).toBeInTheDocument();
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("filters rows by the search field", async () => {
    renderSources();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Search sources"), "report");
    expect(screen.queryByText("brief.pdf")).not.toBeInTheDocument();
    expect(screen.queryByText("broken.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("report.docx")).toBeInTheDocument();
  });

  it("renders the not-found state when the project does not exist", async () => {
    server.use(
      http.get("*/projects/p-1", () =>
        HttpResponse.json({ detail: "project not found" }, { status: 404 }),
      ),
    );
    renderSources();
    expect(await screen.findByText("Project not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to projects" })).toBeInTheDocument();
  });

  it("renders a retryable error state when the project cannot load", async () => {
    let failing = true;
    server.use(
      http.get("*/projects/p-1", () =>
        failing
          ? HttpResponse.json({ detail: "boom" }, { status: 500 })
          : HttpResponse.json({
              id: "p-1",
              name: "Default",
              is_public: false,
              created_at: "2026-10-09T10:00:00Z",
            }),
      ),
    );
    renderSources();
    expect(await screen.findByText("Could not load project.")).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "Try again" });
    failing = false;
    await userEvent.setup().click(retry);
    expect(await screen.findByText("brief.pdf")).toBeInTheDocument();
  });

  it("polls while an upload is in flight and stops once all rows are terminal", async () => {
    let inFlight = true;
    let gets = 0;
    server.use(
      http.get("*/projects/p-1/uploads", () => {
        gets += 1;
        return HttpResponse.json(inFlight ? [queuedUpload] : [readyUpload, failedUpload]);
      }),
    );
    vi.useFakeTimers();
    try {
      renderSources();
      await advance(0);
      expect(gets).toBe(1);
      await advance(2000);
      expect(gets).toBe(2);
      inFlight = false;
      await advance(2000);
      expect(gets).toBe(3);
      // Every row is terminal now: no poll may fire for the next three periods.
      await advance(6000);
      expect(gets).toBe(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows a friendly error state and stops polling when the uploads list fails", async () => {
    let gets = 0;
    server.use(
      http.get("*/projects/p-1/uploads", () => {
        gets += 1;
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );
    vi.useFakeTimers();
    try {
      renderSources();
      // The request fires immediately; the failed response settles on the
      // next clock flush, replacing the skeleton with the error state.
      await advance(0);
      await advance(500);
      expect(screen.getByText("Could not load the source items.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
      // The failure must not read as an empty list: no table, no empty-state copy.
      expect(screen.queryByText("Filename")).not.toBeInTheDocument();
      expect(screen.queryByText("No source items yet.")).not.toBeInTheDocument();

      // From the error state on, no request may fire for three poll periods:
      // whatever ran before the failure was known is the baseline.
      const getsAtError = gets;
      await advance(6000);
      expect(gets).toBe(getsAtError);
    } finally {
      vi.useRealTimers();
    }
  });
});
