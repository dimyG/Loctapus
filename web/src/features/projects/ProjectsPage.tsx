import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
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
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { Link as RouterLink } from "react-router";
import { sectionPath } from "../../app/sectionPaths";
import CreateProjectDialog from "./CreateProjectDialog";
import EmptyProjects from "./EmptyProjects";
import { useGetProjectsQuery } from "./projectsApi";

/** The projects home: searchable list with loading, empty, and error states. */
export default function ProjectsPage() {
  const { data: projects, isLoading, error, refetch } = useGetProjectsQuery();
  // The snackbar stays hidden once dismissed for the current error object;
  // a fresh failure (or a retry) shows it again. It only covers the
  // stale-data case: with nothing cached, the retryable card renders instead.
  const [dismissedError, setDismissedError] = useState<unknown>(null);
  const showError = error !== undefined && error !== dismissedError && (projects?.length ?? 0) > 0;
  const [dialogOpen, setDialogOpen] = useState(false);
  const [search, setSearch] = useState("");
  // The search is a client-side name filter; the endpoint has no query support.
  const needle = search.trim().toLowerCase();
  const visibleProjects = (projects ?? []).filter((project) =>
    project.name.toLowerCase().includes(needle),
  );

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
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <TextField
            size="small"
            label="Search projects"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Button variant="contained" onClick={() => setDialogOpen(true)}>
            Create project
          </Button>
        </Stack>
      </Stack>
      {isLoading ? (
        <Table sx={{ mt: 3 }}>
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
        <Card variant="outlined" sx={{ mt: 3, overflowX: "auto" }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Visibility</TableCell>
                <TableCell>Created</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleProjects.map((project) => (
                <TableRow key={project.id}>
                  <TableCell>
                    <Link component={RouterLink} to={sectionPath("sources", project.id)}>
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
        </Card>
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
