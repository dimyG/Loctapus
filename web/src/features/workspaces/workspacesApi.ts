import { api } from "../../app/api";

/** One workspace as the API returns it. */
export type Workspace = { id: string; name: string };

/** Server state for the workspaces the user belongs to. */
export const workspacesApi = api.injectEndpoints({
  endpoints: (build) => ({
    getWorkspaces: build.query<Workspace[], void>({
      query: () => "/workspaces",
      providesTags: ["Workspace"],
    }),
  }),
});

/** Generated hook listing the workspaces the signed-in user belongs to. */
export const { useGetWorkspacesQuery } = workspacesApi;
