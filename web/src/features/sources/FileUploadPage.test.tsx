import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
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

const PDF_BYTES = "%PDF-1.4 test bytes";

function pdfFile(name: string): File {
  return new File([PDF_BYTES], name, { type: "application/pdf" });
}

/**
 * jsdom and Node's fetch (undici) disagree on Blob realms: undici cannot read
 * a jsdom File's bytes and its multipart parser rejects them, so file uploads
 * would never round-trip. Swapping File and FormData to the Node (undici)
 * classes for this file puts the page, the fetch call, and request.formData()
 * in the same realm, which is how they always are in a real browser.
 */
let realFile: typeof File | undefined;
let realFormData: typeof FormData | undefined;

beforeAll(async () => {
  const { File: NodeFile } = await import("node:buffer");
  // An urlencoded Request body parses into the bundled undici FormData class.
  const probe = await new Request("http://localhost/", {
    method: "POST",
    body: "a=b",
    headers: { "content-type": "application/x-www-form-urlencoded" },
  }).formData();
  realFile = globalThis.File;
  realFormData = globalThis.FormData;
  globalThis.File = NodeFile as unknown as typeof File;
  globalThis.FormData = probe.constructor as unknown as typeof FormData;
});
afterAll(() => {
  if (realFile !== undefined) {
    globalThis.File = realFile;
  }
  if (realFormData !== undefined) {
    globalThis.FormData = realFormData;
  }
});

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

  it("removes the row once the delete completes", async () => {
    let uploads = [queuedUpload, readyUpload, failedUpload];
    server.use(
      http.get("*/projects/p-1/uploads", () => HttpResponse.json(uploads)),
      http.delete("*/projects/p-1/uploads/s-1", () => {
        uploads = uploads.filter((upload) => upload.id !== "s-1");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderUploadPage();
    expect(await screen.findByText("brief.pdf")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Delete brief.pdf" }));
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    // The mutation invalidates the list, so the deleted row vanishes without a reload.
    await waitFor(() => expect(screen.queryByText("brief.pdf")).not.toBeInTheDocument());
    expect(screen.getByText("report.docx")).toBeInTheDocument();
  });

  it("shows an Uploading row while the file is posting and hands off to the queued row", async () => {
    const uploadedRow: Upload = {
      ...queuedUpload,
      id: "s-new",
      filename: "report.pdf",
      created_at: "2026-10-13T09:00:00Z",
    };
    const terminalRows = [readyUpload, failedUpload];
    let posted = false;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("*/projects/p-1/uploads", () =>
        HttpResponse.json(posted ? [uploadedRow, ...terminalRows] : terminalRows),
      ),
      http.post("*/projects/p-1/uploads", async () => {
        await gate;
        posted = true;
        return HttpResponse.json(uploadedRow, { status: 201 });
      }),
    );
    renderUploadPage();
    // The initial list is fully terminal, so no poll interferes with the window.
    expect(await screen.findByText("report.docx")).toBeInTheDocument();
    await userEvent.setup().upload(screen.getByLabelText("Upload"), pdfFile("report.pdf"));
    // While the POST streams the bytes, the row is already there, marked
    // Uploading, and inert: no open button and no delete action yet.
    expect(await screen.findByText("Uploading")).toBeInTheDocument();
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "report.pdf" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete report.pdf" })).not.toBeInTheDocument();
    release();
    // The handoff is seamless: one report.pdf row throughout, chip swapped to Queued.
    expect(await screen.findByText("Queued")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Uploading")).not.toBeInTheDocument());
    expect(screen.getAllByText("report.pdf")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "report.pdf" })).toBeInTheDocument();
  });

  it("drops the Uploading row and shows the alert when the post fails", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("*/projects/p-1/uploads", () => HttpResponse.json([readyUpload, failedUpload])),
      http.post("*/projects/p-1/uploads", async () => {
        await gate;
        return HttpResponse.json(
          { detail: "Could not store the file. Please try again." },
          { status: 503 },
        );
      }),
    );
    renderUploadPage();
    expect(await screen.findByText("report.docx")).toBeInTheDocument();
    await userEvent.setup().upload(screen.getByLabelText("Upload"), pdfFile("report.pdf"));
    expect(await screen.findByText("Uploading")).toBeInTheDocument();
    release();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not store the file. Please try again.",
    );
    await waitFor(() => expect(screen.queryByText("Uploading")).not.toBeInTheDocument());
    expect(screen.queryByText("report.pdf")).not.toBeInTheDocument();
  });

  it("invalidates the list on upload, so the new row appears without a reload", async () => {
    let gets = 0;
    const uploadedRow: Upload = {
      ...queuedUpload,
      id: "s-new",
      filename: "report.pdf",
      created_at: "2026-10-13T09:00:00Z",
    };
    const terminalRows = [readyUpload, failedUpload];
    server.use(
      http.get("*/projects/p-1/uploads", () => {
        gets += 1;
        return HttpResponse.json(gets === 1 ? terminalRows : [...terminalRows, uploadedRow]);
      }),
      http.post("*/projects/p-1/uploads", () => HttpResponse.json(uploadedRow, { status: 201 })),
    );
    renderUploadPage();
    await userEvent.setup().upload(screen.getByLabelText("Upload"), pdfFile("report.pdf"));
    // The mutation invalidates the list, so the table refetches and the
    // freshly created row lands without any manual reload.
    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(gets).toBe(2);
  });
});
