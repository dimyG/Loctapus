import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";
import type { JSX } from "react";
import { Navigate } from "react-router";
import { useAppDispatch } from "../../app/hooks";
import { sectionPath } from "../../app/sectionPaths";
import type { Project } from "../projects/projectsApi";
import { useGetProjectsQuery } from "../projects/projectsApi";
import { uploadsApi } from "../uploads/uploadsApi";

/** Projects newest first: the walk must try the freshest project first. */
function sortNewestFirst(projects: Project[]): Project[] {
  return [...projects].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

/**
 * The internal /app resolver behind the signed-in funnel: walks the user's
 * projects newest-first and lands on the first chattable one's chat, falls
 * back to the newest project's sources, or on /projects with no projects at
 * all. A failed uploads fetch counts as not chattable; the walk continues.
 */
export default function ChatLanding(): JSX.Element {
  const { data: projects, error, refetch } = useGetProjectsQuery();
  const dispatch = useAppDispatch();
  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    if (projects === undefined || projects.length === 0) {
      return;
    }
    // A cancelled walk drops its result: StrictMode double-invokes effects,
    // and only the run that is still alive when the response lands navigates.
    let cancelled = false;
    const ordered = sortNewestFirst(projects);
    // Every initiate handle is unsubscribed on cleanup: the walk only
    // borrows the uploads cache, it never holds a subscription past its exit.
    const handles: Array<{ unsubscribe: () => void }> = [];
    void (async () => {
      for (const project of ordered) {
        // forceRefetch: statuses cached by an earlier visit can be stale,
        // so the decision must come from what the server says now.
        const handle = dispatch(
          uploadsApi.endpoints.getUploads.initiate(project.id, { forceRefetch: true }),
        );
        handles.push(handle);
        const { data } = await handle;
        if (cancelled) {
          return;
        }
        const chattable = data?.some((upload) => upload.status === "ready") ?? false;
        if (chattable) {
          setTarget(sectionPath("chat", project.id));
          return;
        }
      }
      setTarget(sectionPath("sources", ordered[0].id));
    })();
    return () => {
      cancelled = true;
      for (const handle of handles) {
        handle.unsubscribe();
      }
    };
  }, [projects, dispatch]);

  if (error !== undefined && projects === undefined) {
    // Nothing cached and the fetch failed: a retryable card, never a dead end.
    return (
      <Stack spacing={2} sx={{ py: 8, alignItems: "center" }}>
        <Typography color="text.secondary">Could not load projects.</Typography>
        <Button variant="outlined" onClick={() => refetch()}>
          Try again
        </Button>
      </Stack>
    );
  }
  if (projects !== undefined && projects.length === 0) {
    return <Navigate to="/projects" replace />;
  }
  if (target === null) {
    // Covers the projects fetch and the walk: BootSplash would assume the
    // full viewport, but this renders inside the app shell.
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }
  return <Navigate to={target} replace />;
}
