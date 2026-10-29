import type { FetchArgs } from "@reduxjs/toolkit/query";
import { api } from "../../app/api";

/**
 * How long one upload request may run before the client gives up. A connection
 * that stalls mid-body never errors on its own, so without this cap the upload
 * button would stay disabled forever; 360s still fits the 25 MB maximum on a
 * ~0.6 Mbps uplink, the slowest link worth serving.
 */
export const UPLOAD_TIMEOUT_MS = 360_000;

/** The statuses an upload's latest pipeline run can report. */
export type UploadStatus = "queued" | "fetching" | "processing" | "indexing" | "ready" | "failed";

/**
 * A sources-table row's status: the server's vocabulary plus the client-side
 * "uploading", for a file whose bytes are still being posted - the server only
 * learns of the upload when the POST completes.
 */
export type RowStatus = UploadStatus | "uploading";

/** One uploaded file as the uploads endpoints return it. */
export type Upload = {
  id: string;
  project_id: string;
  filename: string;
  status: UploadStatus;
  created_at: string;
};

/** One row of the sources table: a server upload, or an optimistic stand-in. */
export type SourceRow = Omit<Upload, "status"> & { status: RowStatus };

/** Builds the fetch args for one file upload, capping the request at the stall timeout. */
export function uploadFileArgs({ projectId, file }: { projectId: string; file: File }): FetchArgs {
  const formData = new FormData();
  formData.append("file", file);
  return {
    url: `/projects/${projectId}/uploads`,
    method: "POST",
    body: formData,
    timeout: UPLOAD_TIMEOUT_MS,
  };
}

/** Server state for a project's uploads, injected into the base api client. */
export const uploadsApi = api.injectEndpoints({
  endpoints: (build) => ({
    getUploads: build.query<Upload[], string>({
      query: (projectId) => `/projects/${projectId}/uploads`,
      providesTags: (_uploads, _error, projectId) => [{ type: "Upload", id: projectId }],
    }),
    uploadFile: build.mutation<Upload, { projectId: string; file: File }>({
      query: uploadFileArgs,
      // Upsert the created row the moment the server answers, so the table
      // swaps the client's "uploading" stand-in for the real row without
      // waiting for the invalidation refetch - and survives that refetch
      // failing. A retry reuses the item id, so an existing row is replaced.
      onQueryStarted: async ({ projectId }, { dispatch, queryFulfilled }) => {
        try {
          const { data: upload } = await queryFulfilled;
          dispatch(
            uploadsApi.util.updateQueryData("getUploads", projectId, (draft) => {
              const index = draft.findIndex((row) => row.id === upload.id);
              if (index === -1) {
                draft.unshift(upload);
              } else {
                draft[index] = upload;
              }
            }),
          );
        } catch {
          // A failed upload has no row to insert; the caller surfaces the error.
        }
      },
      invalidatesTags: (_upload, _error, { projectId }) => [{ type: "Upload", id: projectId }],
    }),
    deleteUpload: build.mutation<void, { projectId: string; uploadId: string }>({
      query: ({ projectId, uploadId }) => ({
        url: `/projects/${projectId}/uploads/${uploadId}`,
        method: "DELETE",
      }),
      // The row is gone server-side once the 204 lands: drop it from the cache
      // at once instead of letting a slow invalidation refetch invite a second
      // delete of it. The refetch still follows as the authoritative backstop.
      onQueryStarted: async ({ projectId, uploadId }, { dispatch, queryFulfilled }) => {
        try {
          await queryFulfilled;
          dispatch(
            uploadsApi.util.updateQueryData("getUploads", projectId, (draft) =>
              draft.filter((row) => row.id !== uploadId),
            ),
          );
        } catch {
          // A failed delete changes nothing; the caller surfaces the error.
        }
      },
      invalidatesTags: (_result, _error, { projectId }) => [{ type: "Upload", id: projectId }],
    }),
    getUploadRaw: build.query<Blob, { projectId: string; uploadId: string }>({
      // Raw bytes, not JSON: the default JSON response handler would mangle them.
      query: ({ projectId, uploadId }) => ({
        url: `/projects/${projectId}/uploads/${uploadId}/raw`,
        responseHandler: (response) => response.blob(),
      }),
    }),
  }),
});

export const {
  useGetUploadsQuery,
  useUploadFileMutation,
  useDeleteUploadMutation,
  useLazyGetUploadRawQuery,
} = uploadsApi;
