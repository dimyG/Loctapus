import UploadFileRoundedIcon from "@mui/icons-material/UploadFileRounded";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ChangeEvent, DragEvent } from "react";
import { useState } from "react";
import { getErrorMessage } from "../../app/api";
import { MAX_UPLOAD_MB, uploadRejection } from "../uploads/uploadRules";
import { useUploadFileMutation } from "../uploads/uploadsApi";

/** The native file picker, visually folded into the Upload button (MUI pattern). */
const visuallyHiddenInputSx = {
  clip: "rect(0 0 0 0)",
  clipPath: "inset(50%)",
  height: 1,
  overflow: "hidden",
  position: "absolute",
  bottom: 0,
  left: 0,
  whiteSpace: "nowrap",
  width: 1,
} as const;

/**
 * The file-upload dropzone: the client checks, the mutation, and its alert,
 * with drag-and-drop next to the picker. A batch uploads strictly in order
 * and the first failure - a client rejection or a server error - stops it,
 * so later files are never sent. Gestures that arrive while a batch is
 * running are ignored, so two batches can never interleave. Each accepted
 * file is reported to the page when its POST starts (for the "uploading"
 * row) and when its mutation settles either way: on success the real row is
 * already cached by the mutation, on failure the alert carries the error.
 */
export default function UploadDropzone({
  projectId,
  onUploadStart,
  onUploadSettled,
}: {
  projectId: string;
  /** Fires when one accepted file's POST begins. */
  onUploadStart: (file: File) => void;
  /** Fires after one file's POST succeeds or fails; client-rejected files never start. */
  onUploadSettled: (file: File) => void;
}) {
  const [uploadFile] = useUploadFileMutation();
  const [uploadError, setUploadError] = useState<string | null>(null);
  // Spans the whole batch, not each single mutation: between two files the
  // mutation's pending state dips, and that gap must not accept gestures.
  const [batchInFlight, setBatchInFlight] = useState(false);

  /** Runs the client checks per file, then hands each file to the mutation. */
  async function uploadFiles(files: File[]) {
    // An empty pick or drop is a cancelled gesture, not a failed upload; a
    // gesture during a running batch would interleave two batches and break
    // the strictly-in-order guarantee, so both are ignored.
    if (files.length === 0 || batchInFlight) {
      return;
    }
    setUploadError(null);
    setBatchInFlight(true);
    try {
      for (const file of files) {
        const rejection = uploadRejection(file);
        if (rejection !== null) {
          setUploadError(rejection);
          return;
        }
        try {
          onUploadStart(file);
          await uploadFile({ projectId, file }).unwrap();
        } catch (e) {
          setUploadError(getErrorMessage(e));
          return;
        } finally {
          onUploadSettled(file);
        }
      }
    } finally {
      setBatchInFlight(false);
    }
  }

  /** The picker path: the list is copied before the reset clears the input. */
  function handleFilesChosen(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    // Reset the input so picking the same file again still fires change.
    event.target.value = "";
    void uploadFiles(files);
  }

  /** The drag contract: preventing the default on drag-over is what makes the surface a drop target. */
  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
  }

  /** The drop path: the dragged list is read from the data transfer. */
  function handleDrop(event: DragEvent<HTMLDivElement>) {
    // Dropping straight on the hidden input would set its files natively too;
    // preventing the default leaves the batch to this handler alone.
    event.preventDefault();
    void uploadFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <Box
      data-testid="dropzone"
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      sx={{ border: "1px dashed", borderColor: "divider", borderRadius: 1, mt: 3, p: 4 }}
    >
      <Stack spacing={1} sx={{ alignItems: "center" }}>
        <UploadFileRoundedIcon color="primary" sx={{ fontSize: 44 }} />
        <Typography sx={{ fontWeight: 500 }}>Click or drag files to upload</Typography>
        <Typography color="text.secondary" sx={{ textAlign: "center" }}>
          {`Add PDF or DOCX files up to ${MAX_UPLOAD_MB} MB. Each file is stored, processed, and indexed automatically.`}
        </Typography>
        {/* tabIndex -1 keeps the label out of the tab order: the visually */}
        {/* hidden input inside it is the upload control's single tab stop. */}
        <Button variant="contained" component="label" disabled={batchInFlight} tabIndex={-1}>
          Upload
          <Box
            component="input"
            type="file"
            accept=".pdf,.docx"
            multiple
            disabled={batchInFlight}
            onChange={handleFilesChosen}
            sx={visuallyHiddenInputSx}
          />
        </Button>
      </Stack>
      {uploadError !== null && (
        <Alert role="alert" severity="error" sx={{ mt: 2 }}>
          {uploadError}
        </Alert>
      )}
    </Box>
  );
}
