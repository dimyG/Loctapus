import { http } from "msw";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { initialRootState, makeStore } from "../../app/store";
import { server } from "../../test/server";
import { UPLOAD_TIMEOUT_MS, uploadFileArgs, uploadsApi } from "./uploadsApi";

describe("uploadFileArgs", () => {
  it("targets the project's uploads endpoint with POST and the file part", () => {
    const file = new File(["%PDF-1.4 bytes"], "report.pdf", { type: "application/pdf" });
    const args = uploadFileArgs({ projectId: "p-1", file });
    expect(args.url).toBe("/projects/p-1/uploads");
    expect(args.method).toBe("POST");
    expect((args.body as FormData).get("file")).toBe(file);
  });

  it("caps the request at the stall timeout", () => {
    const file = new File(["%PDF-1.4 bytes"], "report.pdf", { type: "application/pdf" });
    const args = uploadFileArgs({ projectId: "p-1", file });
    expect(args.timeout).toBe(UPLOAD_TIMEOUT_MS);
  });
});

describe("uploadFile mutation", () => {
  /**
   * jsdom and Node's fetch (undici) disagree on Blob realms: undici cannot
   * read a jsdom File's bytes, so the multipart body would fail before the
   * request reaches the handler. Swapping File and FormData to the Node
   * (undici) classes for this file keeps the fetch call and the handler in the
   * same realm, as in the browser.
   */
  let realFile: typeof File | undefined;
  let realFormData: typeof FormData | undefined;

  beforeAll(async () => {
    const { File: NodeFile } = await import("node:buffer");
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

  it("aborts a stalled upload at the timeout instead of hanging forever", async () => {
    let requestArrived = false;
    server.use(
      http.post("*/api/projects/p-1/uploads", () => {
        requestArrived = true;
        // A stalled connection: the handler never settles.
        return new Promise(() => {});
      }),
    );
    vi.useFakeTimers();
    try {
      const store = makeStore(initialRootState());
      const file = new File(["%PDF-1.4 bytes"], "report.pdf", { type: "application/pdf" });
      const action = store.dispatch(
        uploadsApi.endpoints.uploadFile.initiate({ projectId: "p-1", file }),
      );
      // Run the microtasks that carry the request into msw, without the clock.
      await vi.advanceTimersByTimeAsync(0);
      expect(requestArrived).toBe(true);
      // Crossing the timeout fires the abort the middleware turns into the error.
      await vi.advanceTimersByTimeAsync(UPLOAD_TIMEOUT_MS);
      let outcome: unknown = "unexpectedly fulfilled";
      try {
        await action.unwrap();
      } catch (error) {
        outcome = error;
      }
      expect(outcome).toMatchObject({ status: "TIMEOUT_ERROR" });
    } finally {
      vi.useRealTimers();
    }
  });
});
