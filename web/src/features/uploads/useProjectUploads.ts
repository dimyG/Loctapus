import { skipToken } from "@reduxjs/toolkit/query";
import type { SerializedError } from "@reduxjs/toolkit";
import type { FetchBaseQueryError } from "@reduxjs/toolkit/query";
import { useMemo } from "react";
import { useAppSelector } from "../../app/hooks";
import type { RootState } from "../../app/store";
import { uploadsApi, useGetUploadsQuery, type Upload } from "./uploadsApi";
import { isTerminal } from "./uploadStatus";

/** Poll period while any row is still moving through the pipeline. */
const POLL_INTERVAL_MS = 2000;

/**
 * Reads a project's cached uploads query result without subscribing to it.
 * Stays private to this module: the page goes through {@link useProjectUploads}.
 */
function selectUploads(projectId: string) {
  return uploadsApi.endpoints.getUploads.select(projectId);
}

/**
 * A project's uploads with their query state, owning the poll period: 2s
 * while any row is non-terminal, 0 once every row is terminal or an
 * uncached fetch failed. The cached reads happen through store selectors
 * memoized per projectId, so they are created once per project and never
 * on every store update.
 */
export function useProjectUploads(
  projectId: string | undefined,
  options: { skip: boolean },
): {
  uploads: Upload[] | undefined;
  isLoading: boolean;
  error: unknown;
  refetch: () => void;
} {
  // The polling interval must reflect the cached list at subscription time,
  // so read it through the store selector before the query hook: the
  // fulfillment render then passes 0 in the same commit and RTK clears the
  // pending poll.
  const selectCachedUploads = useMemo<(state: RootState) => Upload[] | undefined>(
    () =>
      projectId === undefined ? () => undefined : (state) => selectUploads(projectId)(state).data,
    [projectId],
  );
  const cachedUploads = useAppSelector(selectCachedUploads);
  // The cached error is read through the store selector for the same reason
  // as the cached list: it must be available before the query hook call so a
  // failed fetch can drop the polling interval to 0 in the very next commit.
  const selectCachedUploadsError = useMemo<
    (state: RootState) => FetchBaseQueryError | SerializedError | undefined
  >(
    () =>
      projectId === undefined ? () => undefined : (state) => selectUploads(projectId)(state).error,
    [projectId],
  );
  const cachedUploadsError = useAppSelector(selectCachedUploadsError);
  // An error with nothing cached is terminal for polling: retrying on the
  // poll period would hammer a failing endpoint while the page keeps showing
  // no rows. With cached rows the pipeline statuses still decide.
  const uploadsPending =
    cachedUploads === undefined
      ? cachedUploadsError === undefined
      : cachedUploads.some((upload) => !isTerminal(upload.status));
  const {
    data: uploads,
    isLoading,
    error,
    refetch,
  } = useGetUploadsQuery(options.skip || projectId === undefined ? skipToken : projectId, {
    pollingInterval: uploadsPending ? POLL_INTERVAL_MS : 0,
  });
  return { uploads, isLoading, error, refetch };
}
