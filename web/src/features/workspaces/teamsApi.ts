import { api } from "../../app/api";

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

export const { useGetWorkspaceTeamsQuery } = teamsApi;
