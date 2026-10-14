import { describe, expect, it } from "vitest";
import { ALLOWED_EXTENSIONS, MAX_UPLOAD_MB, uploadRejection } from "./uploadRules";

/** A named file of the given size, so no bytes are ever read. */
function file(name: string, bytes: number): File {
  return new File([new ArrayBuffer(bytes)], name, { type: "application/pdf" });
}

describe("MAX_UPLOAD_MB", () => {
  it("pins the backend's 25 MB upload limit", () => {
    expect(MAX_UPLOAD_MB).toBe(25);
  });
});

describe("ALLOWED_EXTENSIONS", () => {
  it("mirrors the server's supported extensions", () => {
    expect([...ALLOWED_EXTENSIONS]).toEqual([".pdf", ".docx"]);
  });
});

describe("uploadRejection", () => {
  it("allows a file inside the limits", () => {
    expect(uploadRejection(file("brief.pdf", 8))).toBeNull();
  });

  it("matches the extension case-insensitively", () => {
    expect(uploadRejection(file("REPORT.DOCX", 8))).toBeNull();
  });

  it("rejects an unsupported extension with the server's copy", () => {
    expect(uploadRejection(file("notes.txt", 8))).toBe("Only PDF and DOCX files are supported.");
  });

  it("rejects an empty file with the server's copy", () => {
    expect(uploadRejection(file("empty.pdf", 0))).toBe("The file is empty.");
  });

  it("rejects a file over the limit with copy derived from MAX_UPLOAD_MB", () => {
    const tooBig = file("big.pdf", MAX_UPLOAD_MB * 1024 * 1024 + 1);
    expect(tooBig.size).toBeGreaterThan(MAX_UPLOAD_MB * 1024 * 1024);
    expect(uploadRejection(tooBig)).toBe(
      `The file is too large. The maximum size is ${MAX_UPLOAD_MB} MB.`,
    );
  });
});
