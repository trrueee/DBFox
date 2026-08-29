import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "../../lib/api/projects";
import type { ProjectCreateRequest, ProjectResponse } from "../../lib/api/generated/types.gen";

export const projectQueryKeys = {
  all: ["projects"] as const,
};

const EMPTY_PROJECTS: Array<ProjectResponse> = [];

/**
 * Project navigation facts for the Workbench Shell.
 *
 * The active project id is owned by the Shell store; this hook only owns the
 * list/create API projection and its cache lifecycle.
 */
export function useProjectState(activeProjectId: string) {
  const queryClient = useQueryClient();
  const projectsQuery = useQuery({
    queryKey: projectQueryKeys.all,
    queryFn: () => projectsApi.listProjects(),
  });
  const projects = projectsQuery.data ?? EMPTY_PROJECTS;
  const activeProject = useMemo(
    () => projects.find((project) => project.id === activeProjectId) ?? null,
    [activeProjectId, projects],
  );

  const invalidateProjects = () =>
    queryClient.invalidateQueries({ queryKey: projectQueryKeys.all });

  const createMutation = useMutation({
    mutationFn: (params: ProjectCreateRequest) => projectsApi.createProject(params),
    onSuccess: invalidateProjects,
  });

  return {
    projects,
    activeProject,
    loadingProjects: projectsQuery.isPending,
    projectError: projectsQuery.error ?? null,
    refreshProjects: async () => {
      await projectsQuery.refetch();
    },
    createProject: createMutation.mutateAsync,
  };
}
