import DeleteOutlineRoundedIcon from "@mui/icons-material/DeleteOutlineRounded";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Snackbar from "@mui/material/Snackbar";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import UploadStatusChip from "../uploads/UploadStatusChip";
import type { SourceRow } from "../uploads/uploadsApi";
import { useDeleteUploadMutation, useLazyGetUploadRawQuery } from "../uploads/uploadsApi";

/**
 * The project's source items in the CRUD template's table-in-card look. Every
 * item today is a file upload, so the Type column is a constant and clicking
 * a filename opens the file itself in a new tab; both grow per type once a
 * second source type exists. Rows delete through a confirm dialog; a failed
 * delete surfaces in a snackbar whose action retries it.
 */
export default function SourceItemsTable({ items }: { items: SourceRow[] }) {
  const [getRaw] = useLazyGetUploadRawQuery();
  const [deleteUpload] = useDeleteUploadMutation();
  // One open at a time across the table: the row whose fetch is in flight,
  // so a second click anywhere is ignored instead of double-opening.
  const [pendingId, setPendingId] = useState<string | null>(null);
  // The row whose open failed, kept so the snackbar's action can retry it.
  const [failedUpload, setFailedUpload] = useState<SourceRow | null>(null);
  // The row the confirm dialog is armed on; null keeps the dialog closed.
  const [deleteCandidate, setDeleteCandidate] = useState<SourceRow | null>(null);
  // The rows whose delete request is in flight, each unrepeatable mid-delete.
  const [deletingIds, setDeletingIds] = useState<ReadonlySet<string>>(new Set());
  // The row whose delete failed, kept so the snackbar's action can retry it.
  const [failedDelete, setFailedDelete] = useState<SourceRow | null>(null);
  // Outlives the armed row so the closing dialog's text survives its exit transition.
  const [shownCandidate, setShownCandidate] = useState<SourceRow | null>(null);

  /** Fetches the upload's raw bytes and opens them as a blob in a new tab. */
  async function openUpload(item: SourceRow) {
    if (pendingId !== null) {
      return;
    }
    setPendingId(item.id);
    try {
      const blob = await getRaw({ projectId: item.project_id, uploadId: item.id }).unwrap();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      // Revoke lazily: the new tab must finish reading the blob before its URL dies.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setFailedUpload(item);
    } finally {
      setPendingId(null);
    }
  }

  /** Fires the delete for one row; a failure keeps the row and offers a retry. */
  async function deleteItem(item: SourceRow) {
    if (deletingIds.has(item.id)) {
      return;
    }
    setDeletingIds((current) => new Set(current).add(item.id));
    try {
      await deleteUpload({ projectId: item.project_id, uploadId: item.id }).unwrap();
    } catch {
      setFailedDelete(item);
    } finally {
      setDeletingIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
    }
  }

  /** Closes the armed dialog and deletes its row. */
  async function confirmDelete() {
    const item = deleteCandidate;
    setDeleteCandidate(null);
    if (item !== null) {
      await deleteItem(item);
    }
  }

  return (
    <>
      <Card variant="outlined" sx={{ mt: 3, overflowX: "auto" }}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Filename</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Created</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>
                  {item.status === "uploading" ? (
                    // The stand-in row's id is client-side, so it can neither
                    // be opened nor deleted until the real row replaces it.
                    item.filename
                  ) : (
                    <Link component="button" type="button" onClick={() => void openUpload(item)}>
                      {item.filename}
                    </Link>
                  )}
                </TableCell>
                <TableCell>File upload</TableCell>
                <TableCell>
                  <UploadStatusChip status={item.status} />
                </TableCell>
                <TableCell>{new Date(item.created_at).toLocaleDateString()}</TableCell>
                <TableCell align="right">
                  {item.status !== "uploading" && (
                    <IconButton
                      aria-label={`Delete ${item.filename}`}
                      disabled={deletingIds.has(item.id)}
                      onClick={() => {
                        setShownCandidate(item);
                        setDeleteCandidate(item);
                      }}
                    >
                      <DeleteOutlineRoundedIcon />
                    </IconButton>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {items.length === 0 && (
          <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
            No source items yet.
          </Typography>
        )}
      </Card>
      <Dialog
        open={deleteCandidate !== null}
        onClose={() => setDeleteCandidate(null)}
        slotProps={{ transition: { onExited: () => setShownCandidate(null) } }}
      >
        <DialogTitle>Delete source item?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {shownCandidate !== null &&
              `"${shownCandidate.filename}" and its indexed content will be permanently deleted.`}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteCandidate(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={() => void confirmDelete()}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={failedUpload !== null}
        autoHideDuration={6000}
        onClose={() => setFailedUpload(null)}
        message="Could not open the file."
        action={
          <Button
            color="inherit"
            size="small"
            onClick={() => {
              const item = failedUpload;
              setFailedUpload(null);
              if (item !== null) {
                void openUpload(item);
              }
            }}
          >
            Try again
          </Button>
        }
      />
      <Snackbar
        open={failedDelete !== null}
        autoHideDuration={6000}
        onClose={() => setFailedDelete(null)}
        message="Could not delete the file."
        action={
          <Button
            color="inherit"
            size="small"
            onClick={() => {
              const item = failedDelete;
              setFailedDelete(null);
              if (item !== null) {
                void deleteItem(item);
              }
            }}
          >
            Try again
          </Button>
        }
      />
    </>
  );
}
