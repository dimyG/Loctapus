import { act, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { initialRootState } from "../../app/store";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import type { Upload } from "../uploads/uploadsApi";
import FileUploadPage from "./FileUploadPage";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

/** Renders the page inside its route so useParams carries the project id. */
function renderUploadPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId/sources/upload" element={<FileUploadPage />} />
    </Routes>,
    { preloadedState: authed(), route: "/projects/p-1/sources/upload" },
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

describe("FileUploadPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the back link, heading, dropzone, and the fixture rows", async () => {
    renderUploadPage();
    expect(screen.getByRole("link", { name: "Back to sources" })).toHaveAttribute(
      "href",
      "/projects/p-1/sources",
    );
    expect(screen.getByRole("heading", { name: "File upload" })).toBeInTheDocument();
    expect(screen.getByText("Click or drag files to upload")).toBeInTheDocument();
    expect(screen.getByLabelText("Upload")).toBeInTheDocument();
    expect(await screen.findByText("brief.pdf")).toBeInTheDocument();
    expect(screen.getByText("report.docx")).toBeInTheDocument();
    expect(screen.getByText("broken.pdf")).toBeInTheDocument();
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders the not-found state when the project does not exist", async () => {
    server.use(
      http.get("*/projects/p-1", () =>
        HttpResponse.json({ detail: "project not found" }, { status: 404 }),
      ),
    );
    renderUploadPage();
    expect(await screen.findByText("Project not found.")).toBeInTheDocument();
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
      renderUploadPage();
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
      renderUploadPage();
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
