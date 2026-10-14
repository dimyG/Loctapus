import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { skipToken } from "@reduxjs/toolkit/query";
import type { SerializedError } from "@reduxjs/toolkit";
import type { FetchBaseQueryError } from "@reduxjs/toolkit/query";
import { Link as RouterLink, useParams } from "react-router";
import DashboardLayout from "../../layouts/DashboardLayout";
import UploadCard from "../uploads/UploadCard";
import UploadsTable from "../uploads/UploadsTable";
import { useProjectUploads } from "../uploads/useProjectUploads";
import { useGetProjectQuery } from "./projectsApi";

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

/** A single project: upload documents and follow their processing statuses. */
export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const {
    data: project,
    error: projectError,
    isLoading: projectLoading,
    refetch: refetchProject,
  } = useGetProjectQuery(projectId ?? skipToken);
  const projectMissing = errorStatus(projectError) === 404;
  const {
    uploads,
    isLoading: uploadsLoading,
    error: uploadsError,
    refetch: refetchUploads,
  } = useProjectUploads(projectId, { skip: projectMissing });

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
      {projectId !== undefined && <UploadCard projectId={projectId} />}
      {uploadsLoading ? (
        <Table sx={{ mt: 3 }}>
          <TableBody>
            {[0, 1, 2].map((row) => (
              <TableRow key={row}>
                {[0, 1, 2].map((cell) => (
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
          <Typography color="text.secondary">
            Could not load the document list. Please try again.
          </Typography>
          <Button variant="outlined" onClick={() => refetchUploads()}>
            Try again
          </Button>
        </Stack>
      ) : (
        <UploadsTable uploads={uploads ?? []} />
      )}
    </DashboardLayout>
  );
}
