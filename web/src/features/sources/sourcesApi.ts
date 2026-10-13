import { api } from "../../app/api";

/** The statuses a source's latest pipeline run can report. */
export type SourceStatus = "queued" | "fetching" | "processing" | "indexing" | "ready" | "failed";

/** One uploaded document as the sources endpoints return it. */
export type Source = {
  id: string;
  project_id: string;
  type: string;
  status: SourceStatus;
  filename: string;
  created_at: string;
};

/** Server state for a project's uploaded sources, injected into the base api client. */
export const sourcesApi = api.injectEndpoints({
  endpoints: (build) => ({
    getSources: build.query<Source[], string>({
      query: (projectId) => `/projects/${projectId}/sources`,
      providesTags: ["Source"],
    }),
    uploadSource: build.mutation<Source, { projectId: string; file: File }>({
      query: ({ projectId, file }) => {
        const formData = new FormData();
        formData.append("file", file);
        return { url: `/projects/${projectId}/sources`, method: "POST", body: formData };
      },
      invalidatesTags: ["Source"],
    }),
  }),
});

/**
 * Reads the cached sources list of one project without subscribing to it. The
 * project page needs the list before its query hook call, so a terminal list
 * can drop the polling interval to 0 in the same render that delivered it.
 */
export const selectSources = (projectId: string) =>
  sourcesApi.endpoints.getSources.select(projectId);

export const { useGetSourcesQuery, useUploadSourceMutation } = sourcesApi;
