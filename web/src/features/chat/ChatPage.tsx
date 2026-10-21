import ChatBubbleRoundedIcon from "@mui/icons-material/ChatBubbleRounded";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { JSX } from "react";
import { Link as RouterLink, useParams } from "react-router";
import { sectionPath } from "../../app/sectionPaths";
import { useProjectGuard } from "../projects/useProjectGuard";
import { useProjectUploads } from "../uploads/useProjectUploads";
import ChatPanel from "./ChatPanel";

/** Shared breadcrumb back to the projects list. */
function BackLink() {
  return (
    <Link component={RouterLink} to="/projects">
      Back to projects
    </Link>
  );
}

/**
 * The project chat page. Readiness comes from the uploads list: the panel
 * exists exactly when a source item is ready, and every other state - the
 * loading placeholder, the retryable error, the upload prompt - explains
 * why there is no thread yet.
 */
export default function ChatPage(): JSX.Element {
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
  const hasReady = (uploads ?? []).some((upload) => upload.status === "ready");

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
  if (uploadsLoading) {
    // The empty state must never flash for a project whose list is in flight.
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }
  if (uploadsError !== undefined && uploads === undefined) {
    // Nothing cached and the fetch failed: a retryable message, never the
    // empty state, which would look identical to a project without sources.
    return (
      <Stack spacing={2} sx={{ py: 8, alignItems: "center" }}>
        <Typography color="text.secondary">Could not load the source items.</Typography>
        <Button variant="outlined" onClick={() => refetchUploads()}>
          Try again
        </Button>
      </Stack>
    );
  }
  if (projectId !== undefined && hasReady) {
    return <ChatPanel projectId={projectId} />;
  }
  return (
    <Stack spacing={2} sx={{ py: 8, alignItems: "center" }}>
      <ChatBubbleRoundedIcon color="primary" sx={{ fontSize: 44 }} />
      <Typography variant="h6" sx={{ fontWeight: 600 }}>
        Upload sources to start asking questions.
      </Typography>
      {projectId !== undefined && (
        <Button variant="contained" component={RouterLink} to={sectionPath("sources", projectId)}>
          Go to sources
        </Button>
      )}
    </Stack>
  );
}
