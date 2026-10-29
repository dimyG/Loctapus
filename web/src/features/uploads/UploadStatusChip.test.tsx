import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../../test/test-utils";
import UploadStatusChip from "./UploadStatusChip";

// Every status a row can show, split by whether it can still move; the
// spinner must track that distinction exactly. "uploading" is client-side:
// the file's bytes are still on their way to the server.
const IN_FLIGHT = [
  { status: "uploading", label: "Uploading" },
  { status: "queued", label: "Queued" },
  { status: "fetching", label: "Fetching" },
  { status: "processing", label: "Processing" },
  { status: "indexing", label: "Indexing" },
] as const;
const TERMINAL = [
  { status: "ready", label: "Ready" },
  { status: "failed", label: "Failed" },
] as const;

describe("UploadStatusChip", () => {
  it.each(IN_FLIGHT)("shows a spinner for the in-flight $status status", ({ status, label }) => {
    renderWithProviders(<UploadStatusChip status={status} />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it.each(TERMINAL)("shows no spinner for the terminal $status status", ({ status, label }) => {
    renderWithProviders(<UploadStatusChip status={status} />);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
