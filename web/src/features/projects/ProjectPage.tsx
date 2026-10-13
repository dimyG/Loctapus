import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { skipToken } from "@reduxjs/toolkit/query";
import type { SerializedError } from "@reduxjs/toolkit";
import type { FetchBaseQueryError } from "@reduxjs/toolkit/query";
import type { ChangeEvent } from "react";
import { useMemo, useState } from "react";
import { Link as RouterLink, useParams } from "react-router";
import { getErrorMessage } from "../../app/api";
import { useAppSelector } from "../../app/hooks";
import type { RootState } from "../../app/store";
import DashboardLayout from "../../layouts/DashboardLayout";
import { useGetProjectQuery } from "./projectsApi";
import {
  selectSources,
  useGetSourcesQuery,
  useUploadSourceMutation,
  type Source,
} from "../sources/sourcesApi";

/** Upload limits mirroring the backend's sources endpoint. */
const MAX_UPLOAD_MB = 25;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".pdf", ".docx"] as const;

/** Poll period while any row is still moving through the pipeline. */
const POLL_INTERVAL_MS = 2000;

/** The status is terminal once the pipeline decided an outcome for it. */
function isTerminal(status: Source["status"]): boolean {
  return status === "ready" || status === "failed";
}

/** Maps a status to its chip: primary while in flight, colored once decided. */
function statusChip(status: Source["status"]): {
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

/**
 * Mirrors the server's upload checks so invalid files never leave the browser.
 * The copy matches the server's 422 messages exactly.
 */
function uploadRejection(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return "Only PDF and DOCX files are supported.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `The file is too large. The maximum size is ${MAX_UPLOAD_MB} MB.`;
  }
  return null;
}

/** A FetchBaseQueryError response failure carries the HTTP status as a number. */
function errorStatus(error: FetchBaseQueryError | SerializedError | undefined): number | null {
  if (error === undefined || !("status" in error) || typeof error.status !== "number") {
    return null;
  }
  return error.status;
}

/** Shared breadcrumb back to the projects list. */
function BackLink() {
  return (
    <Link component={RouterLink} to="/projects">
      Back to projects
    </Link>
  );
}

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

/** A single project: upload documents and follow their processing statuses. */
export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const {
    data: project,
    error: projectError,
    isLoading: projectLoading,
    refetch: refetchProject,
  } = useGetProjectQuery(projectId ?? skipToken);
  const [uploadSource, { isLoading: uploading }] = useUploadSourceMutation();
  const [uploadError, setUploadError] = useState<string | null>(null);

  // The polling interval must reflect the cached list at subscription time, so
  // read it through the store selector before the query hook: the fulfillment
  // render then passes 0 in the same commit and RTK clears the pending poll.
  const selectCachedSources = useMemo<(state: RootState) => Source[] | undefined>(
    () =>
      projectId === undefined ? () => undefined : (state) => selectSources(projectId)(state).data,
    [projectId],
  );
  const cachedSources = useAppSelector(selectCachedSources);
  const projectMissing = errorStatus(projectError) === 404;
  const sourcesPending =
    cachedSources === undefined || cachedSources.some((source) => !isTerminal(source.status));
  const { data: sources, isLoading: sourcesLoading } = useGetSourcesQuery(
    projectMissing || projectId === undefined ? skipToken : projectId,
    { pollingInterval: sourcesPending ? POLL_INTERVAL_MS : 0 },
  );

  /** Runs the client checks, then hands the file to the upload mutation. */
  async function handleFileChosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset the input so picking the same file again still fires change.
    event.target.value = "";
    if (projectId === undefined || file === undefined) {
      return;
    }
    const rejection = uploadRejection(file);
    if (rejection !== null) {
      setUploadError(rejection);
      return;
    }
    setUploadError(null);
    try {
      await uploadSource({ projectId, file }).unwrap();
    } catch (e) {
      setUploadError(getErrorMessage(e));
    }
  }

  if (projectMissing) {
    return (
      <DashboardLayout>
        <Stack spacing={2} sx={{ py: 8, alignItems: "center" }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Project not found.
          </Typography>
          <BackLink />
        </Stack>
      </DashboardLayout>
    );
  }
  if (projectError !== undefined && project === undefined) {
    return (
      <DashboardLayout>
        <Stack spacing={2} sx={{ py: 8, alignItems: "center" }}>
          <Typography color="text.secondary">Could not load project.</Typography>
          <Button variant="outlined" onClick={() => refetchProject()}>
            Try again
          </Button>
          <BackLink />
        </Stack>
      </DashboardLayout>
    );
  }
  return (
    <DashboardLayout>
      <Stack spacing={0.5} sx={{ alignItems: "flex-start" }}>
        <BackLink />
        {project === undefined || projectLoading ? (
          <Skeleton variant="rounded" width={220} height={44} />
        ) : (
          <Typography component="h1" variant="h4" sx={{ fontWeight: 600 }}>
            {project.name}
          </Typography>
        )}
      </Stack>
      <Card variant="outlined" sx={{ mt: 3, p: 3 }}>
        <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Upload documents
          </Typography>
          <Typography color="text.secondary">
            Add PDF or DOCX files up to 25 MB. Each file is stored, processed, and indexed
            automatically.
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
      {sourcesLoading ? (
        <Table sx={{ mt: 3 }}>
          <TableBody>
            {[0, 1, 2].map((row) => (
              <TableRow key={row} data-testid="skeleton-row">
                {[0, 1, 2].map((cell) => (
                  <TableCell key={cell}>
                    <Skeleton />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <Box sx={{ mt: 3, overflowX: "auto" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Filename</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(sources ?? []).map((source) => (
                <TableRow key={source.id}>
                  <TableCell>{source.filename}</TableCell>
                  <TableCell>
                    <Chip size="small" {...statusChip(source.status)} />
                  </TableCell>
                  <TableCell>{new Date(source.created_at).toLocaleDateString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {sources !== undefined && sources.length === 0 && (
            <Typography color="text.secondary" sx={{ mt: 2 }}>
              No documents uploaded yet.
            </Typography>
          )}
        </Box>
      )}
    </DashboardLayout>
  );
}
