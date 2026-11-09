import { api } from "../../app/api";

/** One team as the API returns it. */
export type Team = { id: string; name: string; workspace_id: string };

/** Server state for the teams inside one workspace. */
export const teamsApi = api.injectEndpoints({
  endpoints: (build) => ({
    getWorkspaceTeams: build.query<Team[], string>({
      query: (workspaceId) => `/workspaces/${workspaceId}/teams`,
      providesTags: ["Team"],
    }),
  }),
});

/**
 * Generated hook listing the teams inside one workspace.
 *
 * @param {string} workspaceId - Workspace whose teams the hook fetches.
 */
export const { useGetWorkspaceTeamsQuery } = teamsApi;
