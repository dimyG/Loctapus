import { api } from "../../app/api";

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
  }),
});

export const { useGetProjectsQuery } = projectsApi;
