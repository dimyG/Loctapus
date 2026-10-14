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
  }),
});

/**
 * Reads the cached uploads list of one project without subscribing to it. The
 * project page needs the list before its query hook call, so a terminal list
 * can drop the polling interval to 0 in the same render that delivered it.
 */
export const selectUploads = (projectId: string) =>
  uploadsApi.endpoints.getUploads.select(projectId);

export const { useGetUploadsQuery, useUploadFileMutation } = uploadsApi;
