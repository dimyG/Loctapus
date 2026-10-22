import { api } from "../../app/api";

/** The statuses an upload's latest pipeline run can report. */
export type UploadStatus = "queued" | "fetching" | "processing" | "indexing" | "ready" | "failed";

/** One uploaded file as the uploads endpoints return it. */
export type Upload = {
  id: string;
  project_id: string;
  filename: string;
  status: UploadStatus;
  created_at: string;
};

/** Server state for a project's uploads, injected into the base api client. */
export const uploadsApi = api.injectEndpoints({
  endpoints: (build) => ({
    getUploads: build.query<Upload[], string>({
      query: (projectId) => `/projects/${projectId}/uploads`,
      providesTags: (_uploads, _error, projectId) => [{ type: "Upload", id: projectId }],
    }),
    uploadFile: build.mutation<Upload, { projectId: string; file: File }>({
      query: ({ projectId, file }) => {
        const formData = new FormData();
        formData.append("file", file);
        return { url: `/projects/${projectId}/uploads`, method: "POST", body: formData };
      },
      invalidatesTags: (_upload, _error, { projectId }) => [{ type: "Upload", id: projectId }],
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

export const { useGetUploadsQuery, useUploadFileMutation, useLazyGetUploadRawQuery } = uploadsApi;
