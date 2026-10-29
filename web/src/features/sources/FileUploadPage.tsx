import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router";
import { sectionPath } from "../../app/sectionPaths";
import { useProjectGuard } from "../projects/useProjectGuard";
import { useProjectUploads } from "../uploads/useProjectUploads";
import type { SourceRow } from "../uploads/uploadsApi";
import SourceItemsTable from "./SourceItemsTable";
import UploadDropzone from "./UploadDropzone";

/** One file whose POST is still in flight, shown as an optimistic table row. */
type PendingUpload = {
  filename: string;
  createdAt: string;
};

/** Shared breadcrumb back to the projects list. */
function BackLink() {
  return (
    <Link component={RouterLink} to="/projects">
      Back to projects
    </Link>
  );
}

/** The file-upload page: the dropzone plus this type's source items. */
export default function FileUploadPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const {
    projectMissing,
    projectUncacheableError,
    refetch: refetchProject,
  } = useProjectGuard(projectId);
  // Files whose POST is still streaming; they render as "uploading" rows so
  // the seconds between the upload gesture and the queued row are visible.
  // The dropzone settles each one: on success the mutation has already put
  // the real row in the cache, on failure the dropzone's alert says why.
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const {
    uploads,
    isLoading: uploadsLoading,
    error: uploadsError,
    refetch: refetchUploads,
  } = useProjectUploads(projectId, {
    skip: projectMissing,
    // A poll response requested before the POST commits would overwrite the
    // freshly inserted row with a pre-commit list; the poll waits it out.
    pausePolling: pendingUploads.length > 0,
  });

  if (projectMissing) {
    return (
      <Stack spacing={2} sx={{ py: 8, alignItems: "center" }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          Project not found.
        </Typography>
        <BackLink />
      </Stack>
    );
  }
  if (projectUncacheableError) {
    return (
      <Stack spacing={2} sx={{ py: 8, alignItems: "center" }}>
        <Typography color="text.secondary">Could not load project.</Typography>
        <Button variant="outlined" onClick={() => refetchProject()}>
          Try again
        </Button>
        <BackLink />
      </Stack>
    );
  }

  // Pending uploads lead the list as stand-in rows; a filename the server
  // already has (a retry) instead flips its existing row to the inert
  // "uploading" status, so one file always shows as exactly one row.
  const pendingFilenames = new Set(pendingUploads.map((pending) => pending.filename));
  const serverRows: SourceRow[] = (uploads ?? []).map((upload) =>
    pendingFilenames.has(upload.filename) ? { ...upload, status: "uploading" } : upload,
  );
  const pendingRows: SourceRow[] = pendingUploads
    .filter((pending) => !(uploads ?? []).some((upload) => upload.filename === pending.filename))
    .map((pending) => ({
      id: `pending-${pending.filename}`,
      project_id: projectId ?? "",
      filename: pending.filename,
      status: "uploading",
      created_at: pending.createdAt,
    }));
  const items = [...pendingRows, ...serverRows];

  return (
    <>
      <Stack spacing={0.5} sx={{ pt: 3, alignItems: "flex-start" }}>
        {projectId !== undefined && (
          <Link component={RouterLink} to={sectionPath("sources", projectId)}>
            Back to sources
          </Link>
        )}
        <Typography component="h1" variant="h4" sx={{ fontWeight: 600 }}>
          File upload
        </Typography>
      </Stack>
      {projectId !== undefined && (
        <UploadDropzone
          projectId={projectId}
          onUploadStart={(file) =>
            setPendingUploads((current) => [
              ...current,
              { filename: file.name, createdAt: new Date().toISOString() },
            ])
          }
          onUploadSettled={(file) =>
            setPendingUploads((current) =>
              current.filter((pending) => pending.filename !== file.name),
            )
          }
        />
      )}
      {uploadsLoading ? (
        <Table sx={{ mt: 3 }}>
          <TableBody>
            {[0, 1, 2].map((row) => (
              <TableRow key={row}>
                {[0, 1, 2, 3].map((cell) => (
                  <TableCell key={cell}>
                    <Skeleton />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : uploadsError !== undefined && uploads === undefined ? (
        // Nothing cached and the fetch failed: a retryable message, never a
        // bare table that looks identical to an empty project.
        <Stack spacing={2} sx={{ mt: 3, py: 8, alignItems: "center" }}>
          <Typography color="text.secondary">Could not load the source items.</Typography>
          <Button variant="outlined" onClick={() => refetchUploads()}>
            Try again
          </Button>
        </Stack>
      ) : (
        <SourceItemsTable items={items} />
      )}
    </>
  );
}
