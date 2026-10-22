import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
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
import type { Upload } from "../uploads/uploadsApi";
import { useLazyGetUploadRawQuery } from "../uploads/uploadsApi";

/**
 * The project's source items in the CRUD template's table-in-card look. Every
 * item today is a file upload, so the Type column is a constant and clicking
 * a filename opens the file itself in a new tab; both grow per type once a
 * second source type exists.
 */
export default function SourceItemsTable({ items }: { items: Upload[] }) {
  const [getRaw] = useLazyGetUploadRawQuery();
  // One open at a time across the table: the row whose fetch is in flight,
  // so a second click anywhere is ignored instead of double-opening.
  const [pendingId, setPendingId] = useState<string | null>(null);
  // The row whose open failed, kept so the snackbar's action can retry it.
  const [failedUpload, setFailedUpload] = useState<Upload | null>(null);

  /** Fetches the upload's raw bytes and opens them as a blob in a new tab. */
  async function openUpload(item: Upload) {
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
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>
                  <Link component="button" type="button" onClick={() => void openUpload(item)}>
                    {item.filename}
                  </Link>
                </TableCell>
                <TableCell>File upload</TableCell>
                <TableCell>
                  <UploadStatusChip status={item.status} />
                </TableCell>
                <TableCell>{new Date(item.created_at).toLocaleDateString()}</TableCell>
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
    </>
  );
}
