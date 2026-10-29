import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MockInstance } from "vitest";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import type { Upload } from "../uploads/uploadsApi";
import SourceItemsTable from "./SourceItemsTable";

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
const uploadRows: Upload[] = [queuedUpload, readyUpload, failedUpload];

// jsdom implements neither window.open nor the blob URL API. The URL subclass
// keeps the constructor working for MSW's own request parsing while the two
// blob methods become spies; everything is restored after each test.
const createObjectURLMock = vi.fn<(obj: Blob | MediaSource) => string>(() => "blob:mock");
const revokeObjectURLMock = vi.fn<(url: string) => void>(() => {});
let windowOpenMock: MockInstance;

/** Serves the raw bytes of the ready row's upload. */
function serveRawBytes() {
  server.use(
    http.get(
      "*/api/projects/p-1/uploads/s-2/raw",
      () => new HttpResponse("%PDF-bytes", { headers: { "Content-Type": "application/pdf" } }),
    ),
  );
}

describe("SourceItemsTable", () => {
  beforeEach(() => {
    createObjectURLMock.mockClear();
    revokeObjectURLMock.mockClear();
    vi.stubGlobal(
      "URL",
      class extends URL {
        static createObjectURL = createObjectURLMock;
        static revokeObjectURL = revokeObjectURLMock;
      },
    );
    windowOpenMock = vi.spyOn(window, "open").mockImplementation(() => null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders rows with filename buttons, the constant type, status chips, and created dates", () => {
    renderWithProviders(<SourceItemsTable items={uploadRows} />);
    for (const header of ["Filename", "Type", "Status", "Created"]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    // Every source item today is a file upload; the column stays honest
    // until a second source type exists.
    expect(screen.getAllByText("File upload")).toHaveLength(3);
    for (const row of uploadRows) {
      // Filenames open the file in a new tab, so they are buttons in a
      // link's clothing; nothing in the table routes to the upload page.
      expect(screen.getByRole("button", { name: row.filename })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: row.filename })).not.toBeInTheDocument();
    }
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(
      screen.getByText(new Date("2026-10-12T10:00:00Z").toLocaleDateString()),
    ).toBeInTheDocument();
  });

  it("shows the empty state with zero items", () => {
    renderWithProviders(<SourceItemsTable items={[]} />);
    expect(screen.getByText("No source items yet.")).toBeInTheDocument();
  });

  it("renders an uploading row as inert: no open button and no delete action", () => {
    const uploadingRow: Upload = {
      ...queuedUpload,
      id: "pending-incoming.pdf",
      status: "uploading",
      filename: "incoming.pdf",
    };
    renderWithProviders(<SourceItemsTable items={[uploadingRow]} />);
    expect(screen.getByText("Uploading")).toBeInTheDocument();
    expect(screen.getByText("incoming.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "incoming.pdf" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete incoming.pdf" })).not.toBeInTheDocument();
  });

  it("opens the file in a new tab when the filename is clicked", async () => {
    serveRawBytes();
    renderWithProviders(<SourceItemsTable items={uploadRows} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "report.docx" }));
    await waitFor(() =>
      expect(windowOpenMock).toHaveBeenCalledWith("blob:mock", "_blank", "noopener"),
    );
    expect(createObjectURLMock).toHaveBeenCalledWith(expect.any(Blob));
    expect(windowOpenMock).toHaveBeenCalledTimes(1);
  });

  it("ignores a second click while the open is in flight", async () => {
    let requestCount = 0;
    let release!: () => void;
    // Held pending until both clicks happened, so the second click lands
    // while the first fetch is still in flight.
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("*/api/projects/p-1/uploads/s-2/raw", async () => {
        requestCount += 1;
        await gate;
        return new HttpResponse("%PDF-bytes", {
          headers: { "Content-Type": "application/pdf" },
        });
      }),
    );
    renderWithProviders(<SourceItemsTable items={uploadRows} />);
    const user = userEvent.setup();
    const filename = screen.getByRole("button", { name: "report.docx" });
    await user.click(filename);
    await user.click(filename);
    release();
    await waitFor(() => expect(windowOpenMock).toHaveBeenCalledTimes(1));
    expect(requestCount).toBe(1);
  });

  it("shows a retryable snackbar when the open fails", async () => {
    let requestCount = 0;
    server.use(
      http.get("*/api/projects/p-1/uploads/s-2/raw", () => {
        requestCount += 1;
        // The first open fails; the snackbar's retry then succeeds.
        if (requestCount === 1) {
          return HttpResponse.json({ detail: "No binary content" }, { status: 503 });
        }
        return new HttpResponse("%PDF-bytes", {
          headers: { "Content-Type": "application/pdf" },
        });
      }),
    );
    renderWithProviders(<SourceItemsTable items={uploadRows} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "report.docx" }));
    expect(await screen.findByText("Could not open the file.")).toBeInTheDocument();
    expect(windowOpenMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() =>
      expect(windowOpenMock).toHaveBeenCalledWith("blob:mock", "_blank", "noopener"),
    );
    expect(requestCount).toBe(2);
  });

  it("asks for confirmation and deletes the item on confirm", async () => {
    let deletes = 0;
    server.use(
      http.delete("*/api/projects/p-1/uploads/s-1", () => {
        deletes += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<SourceItemsTable items={uploadRows} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Delete brief.pdf" }));
    // The confirm dialog names the file so the deletion target is unambiguous.
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("brief.pdf");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deletes).toBe(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("keeps the item when the deletion is cancelled", async () => {
    let deletes = 0;
    server.use(
      http.delete("*/api/projects/p-1/uploads/s-1", () => {
        deletes += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<SourceItemsTable items={uploadRows} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Delete brief.pdf" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deletes).toBe(0);
  });

  it("shows a retryable snackbar when the delete fails", async () => {
    let deletes = 0;
    server.use(
      http.delete("*/api/projects/p-1/uploads/s-1", () => {
        deletes += 1;
        // The first delete fails; the snackbar's retry then succeeds.
        if (deletes === 1) {
          return HttpResponse.json({ detail: "backend down" }, { status: 503 });
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<SourceItemsTable items={uploadRows} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Delete brief.pdf" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Could not delete the file.")).toBeInTheDocument();
    // The closing dialog keeps the page aria-hidden until its exit transition ends.
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(deletes).toBe(2));
  });
});
