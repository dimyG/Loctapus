import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import { isTerminal, statusChip } from "./uploadStatus";
import type { RowStatus } from "./uploadsApi";

/**
 * The row's status chip; spins while the status can still move, whether a
 * pipeline stage or the client-side uploading and deleting states.
 *
 * @param {RowStatus} status - Status a sources-table row currently shows.
 */
export default function UploadStatusChip({ status }: { status: RowStatus }) {
  // Terminal statuses decided an outcome, so only in-flight ones earn a spinner.
  const icon = isTerminal(status) ? undefined : <CircularProgress color="inherit" size={12} />;
  // Pin the width to the widest combo ("Processing" plus spinner) so status
  // transitions stop resizing the chip and reflowing the sources table.
  return (
    <Chip
      size="small"
      icon={icon}
      {...statusChip(status)}
      sx={{ minWidth: 104, justifyContent: "center" }}
    />
  );
}
