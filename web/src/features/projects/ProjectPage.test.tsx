import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { initialRootState } from "../../app/store";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import type { Source } from "../sources/sourcesApi";
import ProjectPage from "./ProjectPage";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

/** Renders the page inside its route so useParams carries the project id. */
function renderProject() {
  return renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectPage />} />
    </Routes>,
    { preloadedState: authed(), route: "/projects/p-1" },
  );
}

const queuedSource: Source = {
  id: "s-1",
  project_id: "p-1",
  type: "document",
  status: "queued",
  filename: "brief.pdf",
  created_at: "2026-10-12T10:00:00Z",
};
const readySource: Source = {
  ...queuedSource,
  id: "s-2",
  status: "ready",
  filename: "report.docx",
  created_at: "2026-10-11T10:00:00Z",
};
const failedSource: Source = {
  ...queuedSource,
  id: "s-3",
  status: "failed",
  filename: "broken.pdf",
  created_at: "2026-10-10T10:00:00Z",
};
const sourceRows: Source[] = [queuedSource, readySource, failedSource];

const PDF_BYTES = "%PDF-1.4 test bytes";

function pdfFile(name: string): File {
  return new File([PDF_BYTES], name, { type: "application/pdf" });
}

/** Advances fake timers inside act so store updates and effects flush. */
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
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

describe("ProjectPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the header, back link, upload card, and status chips", async () => {
    renderProject();
    expect(await screen.findByRole("heading", { name: "Default" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to projects" })).toHaveAttribute(
      "href",
      "/projects",
    );
    expect(screen.getByLabelText("Upload")).toBeInTheDocument();
    expect(screen.getByText("brief.pdf")).toBeInTheDocument();
    expect(screen.getByText("report.docx")).toBeInTheDocument();
    expect(screen.getByText("broken.pdf")).toBeInTheDocument();
    // In-flight statuses are primary (blue), terminal ones color the outcome.
    // The color classes sit on the chip root, not on the label span.
    expect(screen.getByText("Queued").closest(".MuiChip-root")).toHaveClass("MuiChip-colorPrimary");
    expect(screen.getByText("Ready").closest(".MuiChip-root")).toHaveClass("MuiChip-colorSuccess");
    expect(screen.getByText("Failed").closest(".MuiChip-root")).toHaveClass("MuiChip-colorError");
    expect(
      screen.getByText(new Date("2026-10-12T10:00:00Z").toLocaleDateString()),
    ).toBeInTheDocument();
  });

  it("uploads the chosen file as multipart form data with a file part", async () => {
    const posts: { contentType: string | null; file: File | null }[] = [];
    let gets = 0;
    server.use(
      http.get("*/projects/p-1/sources", () => {
        gets += 1;
        return HttpResponse.json(sourceRows);
      }),
      http.post("*/projects/p-1/sources", async ({ request }) => {
        posts.push({
          contentType: request.headers.get("content-type"),
          file: (await request.formData()).get("file") as File | null,
        });
        return HttpResponse.json(
          { ...queuedSource, id: "s-new", filename: "report.pdf" },
          { status: 201 },
        );
      }),
    );
    renderProject();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Upload"), pdfFile("report.pdf"));
    await vi.waitFor(() => {
      expect(posts).toHaveLength(1);
    });
    expect(posts[0].contentType).toContain("multipart/form-data");
    expect(posts[0].file?.name).toBe("report.pdf");
    expect(posts[0].file?.size).toBe(PDF_BYTES.length);
    // The mutation invalidates the list, so the table refetches.
    await vi.waitFor(() => {
      expect(gets).toBe(2);
    });
  });

  it("keeps Upload disabled while the request is pending", async () => {
    let resolveRequest: (() => void) | undefined;
    server.use(
      http.post("*/projects/p-1/sources", async () => {
        await new Promise<void>((resolve) => {
          resolveRequest = resolve;
        });
        return HttpResponse.json(queuedSource, { status: 201 });
      }),
    );
    renderProject();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Upload"), pdfFile("pending.pdf"));
    await vi.waitFor(() => {
      expect(resolveRequest).toBeDefined();
      // MUI marks a disabled non-button element with aria-disabled, not the
      // native disabled attribute, which jest-dom's toBeDisabled cannot see.
      expect(screen.getByRole("button", { name: "Upload" })).toHaveAttribute(
        "aria-disabled",
        "true",
      );
    });
    resolveRequest?.();
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Upload" })).not.toHaveAttribute(
        "aria-disabled",
        "true",
      );
    });
  });

  it("rejects a file with an unsupported extension without posting", async () => {
    const posts: unknown[] = [];
    server.use(
      http.post("*/projects/p-1/sources", ({ request }) => {
        posts.push(request);
        return HttpResponse.json(queuedSource, { status: 201 });
      }),
    );
    renderProject();
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(
      await screen.findByLabelText("Upload"),
      new File(["plain text"], "notes.txt", { type: "text/plain" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only PDF and DOCX files are supported.",
    );
    expect(posts).toHaveLength(0);
  });

  it("rejects a file over the 25MB limit without posting", async () => {
    const posts: unknown[] = [];
    server.use(
      http.post("*/projects/p-1/sources", ({ request }) => {
        posts.push(request);
        return HttpResponse.json(queuedSource, { status: 201 });
      }),
    );
    renderProject();
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(
      await screen.findByLabelText("Upload"),
      new File([new ArrayBuffer(25 * 1024 * 1024 + 1)], "big.pdf", { type: "application/pdf" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The file is too large. The maximum size is 25 MB.",
    );
    expect(posts).toHaveLength(0);
  });

  it("shows friendly copy when the server rejects the upload with 422", async () => {
    server.use(
      http.post("*/projects/p-1/sources", () =>
        HttpResponse.json(
          { detail: [{ loc: ["body", "file"], msg: "field required" }] },
          { status: 422 },
        ),
      ),
    );
    renderProject();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Upload"), pdfFile("report.pdf"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Check the highlighted fields and try again.");
    expect(alert).not.toHaveTextContent("field required");
  });

  it("shows friendly copy when storage is unavailable (503)", async () => {
    server.use(
      http.post("*/projects/p-1/sources", () =>
        HttpResponse.json(
          { detail: "Could not store the file. Please try again." },
          { status: 503 },
        ),
      ),
    );
    renderProject();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Upload"), pdfFile("report.pdf"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not store the file. Please try again.",
    );
  });

  it("polls while a source is in flight and stops once all rows are terminal", async () => {
    let inFlight = true;
    let gets = 0;
    server.use(
      http.get("*/projects/p-1/sources", () => {
        gets += 1;
        return HttpResponse.json(inFlight ? [queuedSource] : [readySource, failedSource]);
      }),
    );
    vi.useFakeTimers();
    try {
      renderProject();
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

  it("shows a friendly error state and stops polling when the sources list fails", async () => {
    let gets = 0;
    server.use(
      http.get("*/projects/p-1/sources", () => {
        gets += 1;
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );
    vi.useFakeTimers();
    try {
      renderProject();
      // The request fires immediately; the failed response settles on the
      // next clock flush, replacing the skeleton with the error state.
      await advance(0);
      await advance(500);
      expect(
        screen.getByText("Could not load the document list. Please try again."),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
      // The failure must not read as an empty list: no table, no empty-state copy.
      expect(screen.queryByText("Filename")).not.toBeInTheDocument();
      expect(screen.queryByText("No documents uploaded yet.")).not.toBeInTheDocument();

      // From the error state on, no request may fire for three poll periods:
      // whatever ran before the failure was known is the baseline.
      const getsAtError = gets;
      await advance(6000);
      expect(gets).toBe(getsAtError);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows a not-found state when the project does not exist", async () => {
    server.use(
      http.get("*/projects/p-1", () =>
        HttpResponse.json({ detail: "project not found" }, { status: 404 }),
      ),
    );
    renderProject();
    expect(await screen.findByText("Project not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to projects" })).toBeInTheDocument();
  });
});
