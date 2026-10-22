import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import { isTerminal, statusChip } from "./uploadStatus";
import type { UploadStatus } from "./uploadsApi";

/** The upload's status chip; spins while the ingestion pipeline can still move it. */
export default function UploadStatusChip({ status }: { status: UploadStatus }) {
  // Terminal statuses decided an outcome, so only in-flight ones earn a spinner.
  const icon = isTerminal(status) ? undefined : <CircularProgress color="inherit" size={12} />;
  return <Chip size="small" icon={icon} {...statusChip(status)} />;
}
