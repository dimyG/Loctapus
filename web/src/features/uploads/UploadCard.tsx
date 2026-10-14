import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ChangeEvent } from "react";
import { useState } from "react";
import { getErrorMessage } from "../../app/api";
import { MAX_UPLOAD_MB, uploadRejection } from "./uploadRules";
import { useUploadFileMutation } from "./uploadsApi";

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

/** The upload card: client checks, the mutation, and its alert. */
export default function UploadCard({ projectId }: { projectId: string }) {
  const [uploadFile, { isLoading: uploading }] = useUploadFileMutation();
  const [uploadError, setUploadError] = useState<string | null>(null);

  /** Runs the client checks, then hands the file to the upload mutation. */
  async function handleFileChosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset the input so picking the same file again still fires change.
    event.target.value = "";
    if (file === undefined) {
      return;
    }
    const rejection = uploadRejection(file);
    if (rejection !== null) {
      setUploadError(rejection);
      return;
    }
    setUploadError(null);
    try {
      await uploadFile({ projectId, file }).unwrap();
    } catch (e) {
      setUploadError(getErrorMessage(e));
    }
  }

  return (
    <Card variant="outlined" sx={{ mt: 3, p: 3 }}>
      <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          Upload documents
        </Typography>
        <Typography color="text.secondary">
          {`Add PDF or DOCX files up to ${MAX_UPLOAD_MB} MB. Each file is stored, processed, and indexed automatically.`}
        </Typography>
        {uploadError !== null && (
          <Alert role="alert" severity="error" sx={{ alignSelf: "stretch" }}>
            {uploadError}
          </Alert>
        )}
        <Button variant="contained" component="label" disabled={uploading}>
          Upload
          <Box
            component="input"
            type="file"
            accept=".pdf,.docx"
            disabled={uploading}
            onChange={handleFileChosen}
            sx={visuallyHiddenInputSx}
          />
        </Button>
      </Stack>
    </Card>
  );
}
