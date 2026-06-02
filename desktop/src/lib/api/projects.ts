import { request } from "./client";
import type { Project } from "./types";

export const projectsApi = {
  listProjects: () => request<Project[]>("/projects"),

  createProject: (params: { name: string; description?: string }) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify(params) }),
};
