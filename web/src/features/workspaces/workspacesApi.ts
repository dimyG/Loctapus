import { api } from "../../app/api";

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

export const { useGetWorkspacesQuery } = workspacesApi;
