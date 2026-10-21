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
 * so later files are never sent.
 */
export default function UploadDropzone({ projectId }: { projectId: string }) {
  const [uploadFile, { isLoading: uploading }] = useUploadFileMutation();
  const [uploadError, setUploadError] = useState<string | null>(null);

  /** Runs the client checks per file, then hands each file to the mutation. */
  async function uploadFiles(files: File[]) {
    if (files.length === 0) {
      // An empty pick or drop is a cancelled gesture, not a failed upload.
      return;
    }
    setUploadError(null);
    for (const file of files) {
      const rejection = uploadRejection(file);
      if (rejection !== null) {
        setUploadError(rejection);
        return;
      }
      try {
        await uploadFile({ projectId, file }).unwrap();
      } catch (e) {
        setUploadError(getErrorMessage(e));
        return;
      }
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
        <Button variant="contained" component="label" disabled={uploading} tabIndex={-1}>
          Upload
          <Box
            component="input"
            type="file"
            accept=".pdf,.docx"
            multiple
            disabled={uploading}
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
