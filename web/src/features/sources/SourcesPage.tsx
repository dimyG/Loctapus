import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router";
import { useProjectGuard } from "../projects/useProjectGuard";
import { useProjectUploads } from "../uploads/useProjectUploads";
import AddSourceMenu from "./AddSourceMenu";
import SourceItemsTable from "./SourceItemsTable";

/** Shared breadcrumb back to the projects list. */
function BackLink() {
  return (
    <Link component={RouterLink} to="/projects">
      Back to projects
    </Link>
  );
}

/** The sources index: every source item behind one toolbar with its search and add action. */
export default function SourcesPage() {
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
  const [search, setSearch] = useState("");

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
  // The search is a client-side filename filter; the endpoint has no query support.
  const needle = search.trim().toLowerCase();
  const items = (uploads ?? []).filter((upload) => upload.filename.toLowerCase().includes(needle));

  return (
    <>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        sx={{ pt: 3, justifyContent: "space-between", alignItems: { sm: "center" } }}
      >
        <Typography component="h1" variant="h4" sx={{ fontWeight: 600 }}>
          Sources
        </Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <TextField
            size="small"
            label="Search sources"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          {projectId !== undefined && <AddSourceMenu projectId={projectId} />}
        </Stack>
      </Stack>
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
