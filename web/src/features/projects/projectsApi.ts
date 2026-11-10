import { api } from "../../app/api";

/** One project as the API returns it. */
export type Project = {
  id: string;
  name: string;
  is_public: boolean;
  created_at: string;
};

/** Server state for projects, injected into the base api client. */
export const projectsApi = api.injectEndpoints({
  endpoints: (build) => ({
    getProjects: build.query<Project[], void>({
      query: () => "/projects",
      providesTags: ["Project"],
    }),
    getProject: build.query<Project, string>({
      query: (projectId) => `/projects/${projectId}`,
      providesTags: ["Project"],
    }),
    createProject: build.mutation<Project, { name: string; team_id: string }>({
      query: (body) => ({ url: "/projects", method: "POST", body }),
      invalidatesTags: ["Project"],
    }),
  }),
});

/**
 * Generated hooks for the project endpoints: list all projects, fetch one by
 * id, and create a project on a team. Creating invalidates the Project tag,
 * so the list and detail queries refetch.
 *
 * @param {string} projectId - Project to fetch, passed to useGetProjectQuery.
 * @param {{ name: string; team_id: string }} body - New project's name and team,
 *   passed to useCreateProjectMutation.
 */
export const { useCreateProjectMutation, useGetProjectsQuery, useGetProjectQuery } = projectsApi;
