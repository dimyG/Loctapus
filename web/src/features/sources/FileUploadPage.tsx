import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { Link as RouterLink, useParams } from "react-router";
import { sectionPath } from "../../app/sectionPaths";
import { useProjectGuard } from "../projects/useProjectGuard";
import { useProjectUploads } from "../uploads/useProjectUploads";
import SourceItemsTable from "./SourceItemsTable";
import UploadDropzone from "./UploadDropzone";

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
  const {
    uploads,
    isLoading: uploadsLoading,
    error: uploadsError,
    refetch: refetchUploads,
  } = useProjectUploads(projectId, { skip: projectMissing });

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

  return (
    <>
      <Stack spacing={0.5} sx={{ alignItems: "flex-start" }}>
        {projectId !== undefined && (
          <Link component={RouterLink} to={sectionPath("sources", projectId)}>
            Back to sources
          </Link>
        )}
        <Typography component="h1" variant="h4" sx={{ fontWeight: 600 }}>
          File upload
        </Typography>
      </Stack>
      {projectId !== undefined && <UploadDropzone projectId={projectId} />}
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
        <SourceItemsTable items={uploads ?? []} />
      )}
    </>
  );
}
