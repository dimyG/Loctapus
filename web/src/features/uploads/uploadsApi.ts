import type { FetchArgs } from "@reduxjs/toolkit/query";
import { api } from "../../app/api";

/**
 * How long one upload request may run before the client gives up. A connection
 * that stalls mid-body never errors on its own, so without this cap the upload
 * button would stay disabled forever; 360s still fits the 25 MB maximum on a
 * ~0.6 Mbps uplink, the slowest link worth serving.
 */
export const UPLOAD_TIMEOUT_MS = 360_000;

/**
 * The statuses an upload's latest pipeline run can report, plus "uploading":
 * the client-side state of a file whose bytes are still being posted, which
 * the server never returns because it only learns of the upload at the end.
 */
export type UploadStatus =
  "uploading" | "queued" | "fetching" | "processing" | "indexing" | "ready" | "failed";

/** One uploaded file as the uploads endpoints return it. */
export type Upload = {
  id: string;
  project_id: string;
  filename: string;
  status: UploadStatus;
  created_at: string;
};

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
      // Insert the created row the moment the server answers, so the table
      // swaps the client's "uploading" stand-in for the real row without
      // waiting for the invalidation refetch - and survives that refetch
      // failing. The refetch still follows as the authoritative backstop.
      onQueryStarted: async ({ projectId }, { dispatch, queryFulfilled }) => {
        try {
          const { data: upload } = await queryFulfilled;
          dispatch(
            uploadsApi.util.updateQueryData("getUploads", projectId, (draft) => {
              if (!draft.some((row) => row.id === upload.id)) {
                draft.unshift(upload);
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
