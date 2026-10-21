import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { initialRootState } from "../../app/store";
import { server } from "../../test/server";
import { renderWithProviders } from "../../test/test-utils";
import { MAX_UPLOAD_MB } from "../uploads/uploadRules";
import type { Upload } from "../uploads/uploadsApi";
import UploadDropzone from "./UploadDropzone";

const authed = () => ({
  ...initialRootState(),
  auth: {
    token: "t-1",
    user: { id: "u-1", email: "user@example.test" },
    status: "idle" as const,
  },
});

/** Renders the dropzone standalone; the mutation only needs the api middleware. */
function renderDropzone() {
  return renderWithProviders(<UploadDropzone projectId="p-1" />, { preloadedState: authed() });
}

const queuedUpload: Upload = {
  id: "s-1",
  project_id: "p-1",
  status: "queued",
  filename: "brief.pdf",
  created_at: "2026-10-12T10:00:00Z",
};

const PDF_BYTES = "%PDF-1.4 test bytes";

function pdfFile(name: string): File {
  return new File([PDF_BYTES], name, { type: "application/pdf" });
}

/**
 * Overrides the upload POST, recording each request's content type and file
 * part; every posting test goes through it so assertions share one shape.
 */
function recordUploadPosts() {
  const posts: { contentType: string | null; file: File | null }[] = [];
  server.use(
    http.post("*/projects/p-1/uploads", async ({ request }) => {
      posts.push({
        contentType: request.headers.get("content-type"),
        file: (await request.formData()).get("file") as File | null,
      });
      return HttpResponse.json(
        { ...queuedUpload, id: "s-new", filename: "uploaded.pdf" },
        { status: 201 },
      );
    }),
  );
  return posts;
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

describe("UploadDropzone", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders the upload control with copy derived from the size limit", () => {
    renderDropzone();
    expect(screen.getByText("Click or drag files to upload")).toBeInTheDocument();
    expect(
      screen.getByText(`Add PDF or DOCX files up to ${MAX_UPLOAD_MB} MB.`, { exact: false }),
    ).toBeInTheDocument();
    // The hidden input is the upload control: named "Upload", multi-file.
    expect(screen.getByLabelText("Upload")).toHaveAttribute("multiple");
  });

  it("uploads the chosen file as multipart form data with a file part", async () => {
    const posts = recordUploadPosts();
    renderDropzone();
    await userEvent.setup().upload(screen.getByLabelText("Upload"), pdfFile("report.pdf"));
    await vi.waitFor(() => {
      expect(posts).toHaveLength(1);
    });
    expect(posts[0].contentType).toContain("multipart/form-data");
    expect(posts[0].file?.name).toBe("report.pdf");
    expect(posts[0].file?.size).toBe(PDF_BYTES.length);
  });

  it("keeps Upload disabled while the request is pending", async () => {
    let resolveRequest: (() => void) | undefined;
    server.use(
      http.post("*/projects/p-1/uploads", async () => {
        await new Promise<void>((resolve) => {
          resolveRequest = resolve;
        });
        return HttpResponse.json(queuedUpload, { status: 201 });
      }),
    );
    renderDropzone();
    await userEvent.setup().upload(screen.getByLabelText("Upload"), pdfFile("pending.pdf"));
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
    const posts = recordUploadPosts();
    renderDropzone();
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(
      screen.getByLabelText("Upload"),
      new File(["plain text"], "notes.txt", { type: "text/plain" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only PDF and DOCX files are supported.",
    );
    expect(posts).toHaveLength(0);
  });

  it("rejects a file over the 25MB limit without posting", async () => {
    const posts = recordUploadPosts();
    renderDropzone();
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(
      screen.getByLabelText("Upload"),
      new File([new ArrayBuffer(25 * 1024 * 1024 + 1)], "big.pdf", { type: "application/pdf" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The file is too large. The maximum size is 25 MB.",
    );
    expect(posts).toHaveLength(0);
  });

  it("rejects an empty file without posting", async () => {
    const posts = recordUploadPosts();
    renderDropzone();
    const user = userEvent.setup();
    await user.upload(
      screen.getByLabelText("Upload"),
      new File([], "empty.pdf", { type: "application/pdf" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("The file is empty.");
    expect(posts).toHaveLength(0);
  });

  it("keeps the upload control a single tab stop", async () => {
    renderDropzone();
    const user = userEvent.setup();
    await user.tab();
    // The label Button is removed from the tab order, so the hidden file
    // input is the upload control's only stop in the whole dropzone.
    expect(document.activeElement).toBe(screen.getByLabelText("Upload"));
    await user.tab();
    expect(document.activeElement).not.toBe(screen.getByLabelText("Upload"));
    expect(document.activeElement).not.toBe(screen.getByRole("button", { name: "Upload" }));
  });

  it("shows friendly copy when the server rejects the upload with 422", async () => {
    server.use(
      http.post("*/projects/p-1/uploads", () =>
        HttpResponse.json(
          { detail: [{ loc: ["body", "file"], msg: "field required" }] },
          { status: 422 },
        ),
      ),
    );
    renderDropzone();
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Upload"), pdfFile("report.pdf"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Check the highlighted fields and try again.");
    expect(alert).not.toHaveTextContent("field required");
  });

  it("shows friendly copy when storage is unavailable (503)", async () => {
    server.use(
      http.post("*/projects/p-1/uploads", () =>
        HttpResponse.json(
          { detail: "Could not store the file. Please try again." },
          { status: 503 },
        ),
      ),
    );
    renderDropzone();
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Upload"), pdfFile("report.pdf"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not store the file. Please try again.",
    );
  });

  it("shows the server's 409 copy when the filename already exists", async () => {
    server.use(
      http.post("*/projects/p-1/uploads", () =>
        HttpResponse.json(
          { detail: "A file with this name already exists in this project." },
          { status: 409 },
        ),
      ),
    );
    renderDropzone();
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Upload"), pdfFile("brief.pdf"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A file with this name already exists in this project.",
    );
  });

  it("posts dropped files in order", async () => {
    const posts = recordUploadPosts();
    renderDropzone();
    fireEvent.drop(screen.getByTestId("dropzone"), {
      dataTransfer: { files: [pdfFile("first.pdf"), pdfFile("second.pdf")] },
    });
    await vi.waitFor(() => {
      expect(posts).toHaveLength(2);
    });
    expect(posts.map((post) => post.file?.name)).toEqual(["first.pdf", "second.pdf"]);
  });

  it("stops the batch at the first failure", async () => {
    const posts = recordUploadPosts();
    renderDropzone();
    fireEvent.drop(screen.getByTestId("dropzone"), {
      dataTransfer: {
        files: [pdfFile("good.pdf"), new File(["plain text"], "notes.txt"), pdfFile("never.pdf")],
      },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only PDF and DOCX files are supported.",
    );
    // The rejected file stops the batch: the third file is never sent.
    expect(posts).toHaveLength(1);
    expect(posts[0].file?.name).toBe("good.pdf");
  });

  it("ignores an empty drop", () => {
    const posts = recordUploadPosts();
    renderDropzone();
    fireEvent.drop(screen.getByTestId("dropzone"), { dataTransfer: { files: [] } });
    expect(posts).toHaveLength(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ignores a second gesture while a batch is in flight", async () => {
    const posts: { file: File | null }[] = [];
    let resolveFirst: (() => void) | undefined;
    server.use(
      http.post("*/projects/p-1/uploads", async ({ request }) => {
        posts.push({ file: (await request.formData()).get("file") as File | null });
        // Only the first POST hangs: a leaked second POST (the bug) would
        // return immediately, so the test can settle every request it sees.
        if (resolveFirst === undefined) {
          await new Promise<void>((resolve) => {
            resolveFirst = resolve;
          });
        }
        return HttpResponse.json(
          { ...queuedUpload, id: "s-new", filename: "uploaded.pdf" },
          { status: 201 },
        );
      }),
    );
    renderDropzone();
    fireEvent.drop(screen.getByTestId("dropzone"), {
      dataTransfer: { files: [pdfFile("first.pdf")] },
    });
    await vi.waitFor(() => {
      expect(resolveFirst).toBeDefined();
    });
    // The batch spans the whole pending request, so a second drop mid-batch
    // must not start a second, interleaved batch.
    fireEvent.drop(screen.getByTestId("dropzone"), {
      dataTransfer: { files: [pdfFile("second.pdf")] },
    });
    resolveFirst?.();
    await vi.waitFor(() => {
      expect(screen.getByRole("button", { name: "Upload" })).not.toHaveAttribute(
        "aria-disabled",
        "true",
      );
    });
    expect(posts).toHaveLength(1);
    expect(posts[0].file?.name).toBe("first.pdf");
  });
});
