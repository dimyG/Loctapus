import { describe, expect, it } from "vitest";
import type { UploadStatus } from "./uploadsApi";
import { isTerminal, statusChip } from "./uploadStatus";

describe("isTerminal", () => {
  it("ends the pipeline on ready", () => {
    expect(isTerminal("ready")).toBe(true);
  });

  it("ends the pipeline on failed", () => {
    expect(isTerminal("failed")).toBe(true);
  });

  it("keeps every in-flight stage non-terminal", () => {
    const inFlight: UploadStatus[] = ["queued", "fetching", "processing", "indexing"];
    for (const status of inFlight) {
      expect(isTerminal(status)).toBe(false);
    }
  });
});

describe("statusChip", () => {
  it("labels every status with its capitalized name", () => {
    const statuses: UploadStatus[] = [
      "queued",
      "fetching",
      "processing",
      "indexing",
      "ready",
      "failed",
    ];
    for (const status of statuses) {
      const label = `${status.charAt(0).toUpperCase()}${status.slice(1)}`;
      expect(statusChip(status).label).toBe(label);
    }
  });

  it("colors ready success and failed error", () => {
    expect(statusChip("ready").color).toBe("success");
    expect(statusChip("failed").color).toBe("error");
  });

  it("colors every in-flight stage primary", () => {
    const inFlight: UploadStatus[] = ["queued", "fetching", "processing", "indexing"];
    for (const status of inFlight) {
      expect(statusChip(status).color).toBe("primary");
    }
  });
});
