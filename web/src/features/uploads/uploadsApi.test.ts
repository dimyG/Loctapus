import { describe, expect, it } from "vitest";
import { UPLOAD_TIMEOUT_MS, uploadFileArgs } from "./uploadsApi";

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
