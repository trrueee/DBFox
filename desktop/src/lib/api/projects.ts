import {
  apiCreateProjectApiV1ProjectsPost,
  apiListProjectsApiV1ProjectsGet,
} from "./generated/sdk.gen";
import type { ProjectCreateRequest, ProjectResponse } from "./generated/types.gen";

export const projectsApi = {
  async listProjects(): Promise<Array<ProjectResponse>> {
    const { data } = await apiListProjectsApiV1ProjectsGet({
      throwOnError: true,
    });
    return data ?? [];
  },

  async createProject(params: ProjectCreateRequest): Promise<ProjectResponse> {
    const { data } = await apiCreateProjectApiV1ProjectsPost({
      body: params,
      throwOnError: true,
    });
    return data;
  },
};
