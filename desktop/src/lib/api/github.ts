import {
  getBindingsApiV1ProjectsProjectIdGithubBindingsGet,
  createBindingApiV1ProjectsProjectIdGithubBindingsPost,
  deleteBindingRouteApiV1ProjectsProjectIdGithubBindingsBindingIdDelete,
  refreshBindingRouteApiV1ProjectsProjectIdGithubBindingsBindingIdRefreshPost,
  listBindingFilesApiV1ProjectsProjectIdGithubBindingsBindingIdFilesGet,
  readBindingFileApiV1ProjectsProjectIdGithubBindingsBindingIdFileGet,
} from "./generated/sdk.gen";
import type {
  GithubBindingResponse,
  GithubFileContentResponse,
  GithubFileListResponse,
} from "./generated/types.gen";

export const githubApi = {
  async listBindings(projectId: string): Promise<GithubBindingResponse[]> {
    const { data } = await getBindingsApiV1ProjectsProjectIdGithubBindingsGet({
      path: { project_id: projectId },
      throwOnError: true,
    });
    return data ?? [];
  },

  async createBinding(
    projectId: string,
    repository: string,
    refName: string = "main",
  ): Promise<GithubBindingResponse> {
    const { data } = await createBindingApiV1ProjectsProjectIdGithubBindingsPost({
      path: { project_id: projectId },
      body: { repository, ref_name: refName },
      throwOnError: true,
    });
    return data;
  },

  async deleteBinding(projectId: string, bindingId: string): Promise<void> {
    await deleteBindingRouteApiV1ProjectsProjectIdGithubBindingsBindingIdDelete({
      path: { project_id: projectId, binding_id: bindingId },
      throwOnError: true,
    });
  },

  async refreshBinding(projectId: string, bindingId: string): Promise<GithubBindingResponse> {
    const { data } = await refreshBindingRouteApiV1ProjectsProjectIdGithubBindingsBindingIdRefreshPost({
      path: { project_id: projectId, binding_id: bindingId },
      throwOnError: true,
    });
    return data;
  },

  async listFiles(
    projectId: string,
    bindingId: string,
    dirPath: string = "",
    limit?: number,
  ): Promise<GithubFileListResponse> {
    const { data } = await listBindingFilesApiV1ProjectsProjectIdGithubBindingsBindingIdFilesGet({
      path: { project_id: projectId, binding_id: bindingId },
      query: { path: dirPath || undefined, limit },
      throwOnError: true,
    });
    return data;
  },

  async readFile(
    projectId: string,
    bindingId: string,
    filePath: string,
  ): Promise<GithubFileContentResponse> {
    const { data } = await readBindingFileApiV1ProjectsProjectIdGithubBindingsBindingIdFileGet({
      path: { project_id: projectId, binding_id: bindingId },
      query: { path: filePath },
      throwOnError: true,
    });
    return data;
  },
};
