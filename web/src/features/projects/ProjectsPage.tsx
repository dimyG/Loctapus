import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Skeleton from "@mui/material/Skeleton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { Link as RouterLink } from "react-router";
import CreateProjectDialog from "./CreateProjectDialog";
import EmptyProjects from "./EmptyProjects";
import { useGetProjectsQuery } from "./projectsApi";

/** The projects home: list with loading, empty, and error states. */
export default function ProjectsPage() {
  const { data: projects, isLoading, error, refetch } = useGetProjectsQuery();
  // The snackbar stays hidden once dismissed for the current error object;
  // a fresh failure (or a retry) shows it again. It only covers the
  // stale-data case: with nothing cached, the retryable card renders instead.
  const [dismissedError, setDismissedError] = useState<unknown>(null);
  const showError = error !== undefined && error !== dismissedError && (projects?.length ?? 0) > 0;
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={2}
        sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
      >
        <Typography component="h1" variant="h4" sx={{ fontWeight: 600 }}>
          Projects
        </Typography>
        <Button variant="contained" onClick={() => setDialogOpen(true)}>
          Create project
        </Button>
      </Stack>
      {isLoading ? (
        <Table>
          <TableBody>
            {[0, 1, 2, 3, 4].map((row) => (
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
      ) : error !== undefined && projects === undefined ? (
        // Nothing cached and the fetch failed: a retryable card, never a
        // dead end (the snackbar below would auto-hide behind this case).
        <Stack spacing={2} sx={{ py: 8, alignItems: "center" }}>
          <Typography color="text.secondary">Could not load projects.</Typography>
          <Button variant="outlined" onClick={() => refetch()}>
            Try again
          </Button>
        </Stack>
      ) : projects !== undefined && projects.length === 0 ? (
        <EmptyProjects onCreate={() => setDialogOpen(true)} />
      ) : (
        <Box sx={{ overflowX: "auto" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Visibility</TableCell>
                <TableCell>Created</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(projects ?? []).map((project) => (
                <TableRow key={project.id}>
                  <TableCell>
                    <Link component={RouterLink} to={`/projects/${project.id}`}>
                      {project.name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={project.is_public ? "Public" : "Private"}
                      variant={project.is_public ? "filled" : "outlined"}
                    />
                  </TableCell>
                  <TableCell>{new Date(project.created_at).toLocaleDateString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
      <Snackbar
        open={showError}
        autoHideDuration={6000}
        onClose={() => setDismissedError(error)}
        message="Could not load projects."
        action={
          <Button
            color="inherit"
            size="small"
            onClick={() => {
              setDismissedError(error);
              refetch();
            }}
          >
            Try again
          </Button>
        }
      />
      {dialogOpen && <CreateProjectDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />}
    </>
  );
}
