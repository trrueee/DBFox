import type { PropsWithChildren } from "react";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { projectsApi } from "../../../lib/api/projects";
import type { ProjectResponse } from "../../../lib/api/generated/types.gen";
import { useProjectState } from "../useProjectState";

vi.mock("../../../lib/api/projects", () => ({
  projectsApi: {
    listProjects: vi.fn(),
    createProject: vi.fn(),
  },
}));

const project: ProjectResponse = {
  id: "project-1",
  name: "订单分析",
  datasource_count: 2,
  status: "active",
};

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("useProjectState", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(projectsApi.listProjects).mockResolvedValue([project]);
  });

  it("loads the real Project list and resolves the active project by Shell id", async () => {
    const { result } = renderHook(
      () => useProjectState("project-1"),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.loadingProjects).toBe(false));
    expect(projectsApi.listProjects).toHaveBeenCalledTimes(1);
    expect(result.current.projects).toEqual([project]);
    expect(result.current.activeProject?.id).toBe("project-1");
  });

  it("returns null for an active project id not present in the real list", async () => {
    const { result } = renderHook(
      () => useProjectState("project-missing"),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.loadingProjects).toBe(false));
    expect(result.current.activeProject).toBeNull();
  });
});
