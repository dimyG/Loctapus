import { skipToken } from "@reduxjs/toolkit/query";
import type { FetchBaseQueryError } from "@reduxjs/toolkit/query";
import type { SerializedError } from "@reduxjs/toolkit";
import { useGetProjectQuery } from "./projectsApi";
import type { Project } from "./projectsApi";

/** A FetchBaseQueryError response failure carries the HTTP status as a number. */
function errorStatus(error: FetchBaseQueryError | SerializedError | undefined): number | null {
  if (error === undefined || !("status" in error) || typeof error.status !== "number") {
    return null;
  }
  return error.status;
}

/**
 * The one project-scope guard every project-scoped page goes through, so the
 * loading, 404, and retryable-error decisions cannot drift between them.
 * The pages render the states; this hook owns the flags: `projectMissing`
 * drives the "Project not found." state and `projectUncacheableError` the
 * retryable "Could not load project." state (an error with nothing cached;
 * stale cached data renders normally instead).
 */
export function useProjectGuard(projectId: string | undefined): {
  project: Project | undefined;
  projectMissing: boolean;
  projectUncacheableError: boolean;
  projectLoading: boolean;
  refetch: () => void;
} {
  const { data: project, error, isLoading, refetch } = useGetProjectQuery(projectId ?? skipToken);
  return {
    project,
    projectMissing: errorStatus(error) === 404,
    projectUncacheableError: error !== undefined && project === undefined,
    projectLoading: isLoading,
    refetch,
  };
}
