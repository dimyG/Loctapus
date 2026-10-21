import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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

describe("SourceItemsTable", () => {
  it("renders rows with filename links, the constant type, status chips, and created dates", () => {
    renderWithProviders(<SourceItemsTable items={uploadRows} />);
    for (const header of ["Filename", "Type", "Status", "Created"]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    // Every source item today is a file upload; the column stays honest
    // until a second source type exists.
    expect(screen.getAllByText("File upload")).toHaveLength(3);
    for (const row of uploadRows) {
      expect(screen.getByRole("link", { name: row.filename })).toHaveAttribute(
        "href",
        `/projects/${row.project_id}/sources/upload`,
      );
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
});
