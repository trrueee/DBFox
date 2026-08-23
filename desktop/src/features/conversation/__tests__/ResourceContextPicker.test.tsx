import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResourceContextPicker } from "../ResourceContextPicker";

const listProjectResources = vi.fn();

afterEach(() => {
  cleanup();
  listProjectResources.mockReset();
});

vi.mock("../../resources/projectResourceRepository", () => ({
  listProjectResources: (...args: unknown[]) => listProjectResources(...args),
}));

describe("ResourceContextPicker", () => {
  it("makes selected authority visible and removable without changing UI focus", async () => {
    listProjectResources.mockResolvedValueOnce([
      { kind: "dbfox.data.database", id: "db-1", name: "billing", version: 4, is_default: true },
    ]);
    const onChange = vi.fn();

    renderPicker(
      <ResourceContextPicker
        projectId="project-1"
        selected={[{ kind: "dbfox.data.database", id: "db-1" }]}
        onChange={onChange}
      />,
    );

    expect(await screen.findByText("billing")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "从对话上下文移除 billing" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("adds a discovered resource only after an explicit user choice", async () => {
    listProjectResources.mockResolvedValueOnce([
      { kind: "dbfox.data.database", id: "db-1", name: "billing", version: 4, is_default: true },
      { kind: "workspace", id: "project-1", name: "workspace", version: 2, is_default: false },
    ]);
    const onChange = vi.fn();

    renderPicker(
      <ResourceContextPicker projectId="project-1" selected={[]} onChange={onChange} />,
    );

    await waitFor(() => expect(listProjectResources).toHaveBeenCalledWith("project-1"));
    fireEvent.pointerDown(screen.getByRole("button", { name: "添加 Agent 上下文" }), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: /billing/ }));
    expect(onChange).toHaveBeenCalledWith([{ kind: "dbfox.data.database", id: "db-1" }]);
  });
});

function renderPicker(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      {node}
    </QueryClientProvider>,
  );
}
