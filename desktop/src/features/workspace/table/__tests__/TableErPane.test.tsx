import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TableErPane } from "../TableErPane";

const apiMocks = vi.hoisted(() => ({
  request: vi.fn(),
}));

const erDiagramMocks = vi.hoisted(() => ({
  props: [] as Array<{
    data: unknown;
    focusTable?: string | null;
    depth?: 1 | 2;
    viewMode?: "focus" | "module" | "full";
    showInferred?: boolean;
    onNodeClick?: (tableName: string) => void;
  }>,
}));

vi.mock("../../../../lib/api/client", () => apiMocks);

vi.mock("../../../../components/ErDiagram", () => ({
  ErDiagram: (props: (typeof erDiagramMocks.props)[number]) => {
    erDiagramMocks.props.push(props);
    return (
      <div
        data-testid="er-diagram"
        data-focus-table={props.focusTable ?? ""}
        data-view-mode={props.viewMode ?? ""}
        data-depth={String(props.depth ?? "")}
        data-show-inferred={String(props.showInferred)}
      >
        <button type="button" onClick={() => props.onNodeClick?.("orders")}>
          focus orders
        </button>
      </div>
    );
  },
}));

const diagramData = {
  nodes: [
    {
      id: "users",
      label: "users",
      comment: "用户",
      module_tag: "account",
      fields: [
        { name: "id", type: "bigint", is_pk: true, is_fk: false },
        { name: "org_id", type: "bigint", is_pk: false, is_fk: true },
      ],
    },
    {
      id: "orders",
      label: "orders",
      comment: "订单",
      module_tag: "billing",
      fields: [
        { name: "id", type: "bigint", is_pk: true, is_fk: false },
        { name: "user_id", type: "bigint", is_pk: false, is_fk: true },
      ],
    },
  ],
  edges: [
    {
      id: "fk-orders-user_id__to__users-id",
      source: "orders",
      sourceHandle: "user_id",
      target: "users",
      targetHandle: "id",
      edge_type: "real",
      label: "FK",
    },
    {
      id: "inf-users-org_id__to__orders-id",
      source: "users",
      sourceHandle: "org_id",
      target: "orders",
      targetHandle: "id",
      edge_type: "inferred",
      label: "推断",
    },
  ],
};

describe("TableErPane", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    erDiagramMocks.props = [];
  });

  it("renders the real ER diagram with focused controls instead of static cards", async () => {
    apiMocks.request.mockResolvedValue(diagramData);

    render(<TableErPane tableId="users" datasourceId="ds-1" />);

    const graph = await screen.findByTestId("er-diagram");
    expect(graph.dataset.focusTable).toBe("users");
    expect(graph.dataset.viewMode).toBe("focus");
    expect(graph.dataset.depth).toBe("1");
    expect(graph.dataset.showInferred).toBe("true");
    expect(screen.getByText("2 张表 · 2 条关系 · 1 条推断")).toBeTruthy();
    expect(screen.queryByRole("option", { name: "模块" })).toBeNull();

    chooseSelectOption("关系深度", "两跳");
    await waitFor(() => expect(erDiagramMocks.props.at(-1)?.depth).toBe(2));

    chooseSelectOption("视图范围", "全库");
    await waitFor(() => expect(erDiagramMocks.props.at(-1)?.viewMode).toBe("full"));

    fireEvent.click(screen.getByRole("button", { name: "隐藏推断关系" }));
    await waitFor(() => expect(erDiagramMocks.props.at(-1)?.showInferred).toBe(false));

    fireEvent.click(screen.getByRole("button", { name: "focus orders" }));
    await waitFor(() => expect(erDiagramMocks.props.at(-1)?.focusTable).toBe("orders"));
  });

  it("shows an explicit empty state instead of a fake diagram when no relationships exist", async () => {
    apiMocks.request.mockResolvedValue({
      nodes: [diagramData.nodes[0]],
      edges: [],
    });

    render(<TableErPane tableId="users" datasourceId="ds-1" />);

    expect(await screen.findByText("暂无可视化关系")).toBeTruthy();
    expect(screen.queryByTestId("er-diagram")).toBeNull();
  });

  it("resets focused controls when table changes without refetching the datasource diagram", async () => {
    apiMocks.request.mockResolvedValue(diagramData);

    const { rerender } = render(<TableErPane tableId="users" datasourceId="ds-1" />);

    await screen.findByTestId("er-diagram");
    chooseSelectOption("关系深度", "两跳");
    chooseSelectOption("视图范围", "全库");
    fireEvent.click(screen.getByRole("button", { name: "隐藏推断关系" }));

    await waitFor(() => {
      expect(erDiagramMocks.props.at(-1)?.depth).toBe(2);
      expect(erDiagramMocks.props.at(-1)?.viewMode).toBe("full");
      expect(erDiagramMocks.props.at(-1)?.showInferred).toBe(false);
    });

    rerender(<TableErPane tableId="orders" datasourceId="ds-1" />);

    await waitFor(() => {
      expect(erDiagramMocks.props.at(-1)?.focusTable).toBe("orders");
      expect(erDiagramMocks.props.at(-1)?.depth).toBe(1);
      expect(erDiagramMocks.props.at(-1)?.viewMode).toBe("focus");
      expect(erDiagramMocks.props.at(-1)?.showInferred).toBe(true);
    });
    expect(apiMocks.request).toHaveBeenCalledTimes(1);
  });
});

function chooseSelectOption(label: string, optionName: string) {
  fireEvent.pointerDown(screen.getByRole("combobox", { name: label }), {
    button: 0,
    ctrlKey: false,
    pointerId: 1,
    pointerType: "mouse",
  });
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}
