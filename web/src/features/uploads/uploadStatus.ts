import type { UploadStatus } from "./uploadsApi";

/** The status is terminal once the pipeline decided an outcome for it. */
export function isTerminal(status: UploadStatus): boolean {
  return status === "ready" || status === "failed";
}

/** Maps a status to its chip: primary while in flight, colored once decided. */
export function statusChip(status: UploadStatus): {
  label: string;
  color: "primary" | "success" | "error";
} {
  const label = `${status.charAt(0).toUpperCase()}${status.slice(1)}`;
  if (status === "ready") {
    return { label, color: "success" };
  }
  if (status === "failed") {
    return { label, color: "error" };
  }
  return { label, color: "primary" };
}
