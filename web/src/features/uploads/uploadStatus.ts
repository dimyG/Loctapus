import type { RowStatus } from "./uploadsApi";

/**
 * Whether the status has a decided outcome: only the server's ready and
 * failed have; the pipeline's in-flight stages and the client-side uploading
 * and deleting states do not.
 *
 * @param {RowStatus} status - Status a sources-table row currently shows.
 */
export function isTerminal(status: RowStatus): boolean {
  return status === "ready" || status === "failed";
}

/**
 * Maps a status to its chip: primary while in flight, colored once decided,
 * except deleting which reads error while it runs - the red flags the
 * destructive action, and the spinner tells it apart from a decided failure.
 *
 * @param {RowStatus} status - Status a sources-table row currently shows.
 */
export function statusChip(status: RowStatus): {
  label: string;
  color: "primary" | "success" | "error";
} {
  const label = `${status.charAt(0).toUpperCase()}${status.slice(1)}`;
  if (status === "failed" || status === "deleting") {
    return { label, color: "error" };
  }
  if (status === "ready") {
    return { label, color: "success" };
  }
  return { label, color: "primary" };
}
