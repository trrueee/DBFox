import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Tree } from "../tree";

interface Node {
  id: string;
  label: string;
  children?: Node[];
}

const root: Node = {
  id: "root",
  label: "",
  children: [
    {
      id: "src",
      label: "src",
      children: [{ id: "src/app.tsx", label: "app.tsx" }],
    },
    { id: "readme", label: "README.md" },
  ],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Host Tree primitive", () => {
  it("uses Zag keyboard/selection behavior without emitting CSP-blocked inline styles", async () => {
    const onItemSelect = vi.fn();
    const { container } = render(
      <Tree
        rootItem={root}
        ariaLabel="Project files"
        getItemId={(item) => item.id}
        getItemLabel={(item) => item.label}
        getItemChildren={(item) => item.children}
        defaultExpandedIds={["src"]}
        onItemSelect={onItemSelect}
      />,
    );

    const tree = screen.getByRole("tree", { name: "Project files" });
    const branch = screen.getByRole("button", { name: "src" });
    expect(screen.getByRole("treeitem", { name: "app.tsx" })).toBeTruthy();

    fireEvent.click(screen.getByRole("treeitem", { name: "README.md" }));
    await waitFor(() => expect(onItemSelect).toHaveBeenCalledWith(root.children?.[1]));

    branch.focus();
    fireEvent.keyDown(tree, { key: "ArrowDown" });
    expect(container.querySelectorAll("[style]")).toHaveLength(0);
  });

  it("loads branch children through Zag and exposes loading errors for an in-place retry", async () => {
    const remoteRoot: Node = {
      id: "root",
      label: "",
      children: [{ id: "remote", label: "Remote catalog" }],
    };
    const loadItemChildren = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce([{ id: "remote/orders", label: "orders" }]);

    const { container } = render(
      <Tree
        rootItem={remoteRoot}
        ariaLabel="Remote resources"
        getItemId={(item) => item.id}
        getItemLabel={(item) => item.label}
        getItemChildren={(item) => item.children}
        getItemChildrenCount={(item) => item.id === "remote" ? 1 : item.children?.length}
        loadItemChildren={loadItemChildren}
        renderItemMeta={(_item, state) => state.loadError ? "读取失败，点击重试" : null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Remote catalog" }));
    expect(await screen.findByText("读取失败，点击重试")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Remote catalog" }));
    expect(await screen.findByRole("treeitem", { name: "orders" })).toBeTruthy();
    expect(loadItemChildren).toHaveBeenCalledTimes(2);
    expect(container.querySelectorAll("[style]")).toHaveLength(0);
  });

  it("discards an async branch result after the authoritative root changes", async () => {
    let resolveOldChildren: ((children: Node[]) => void) | undefined;
    const oldChildren = new Promise<Node[]>((resolve) => {
      resolveOldChildren = resolve;
    });
    const oldRoot: Node = {
      id: "old-root",
      label: "",
      children: [{ id: "old-remote", label: "Old remote" }],
    };
    const newRoot: Node = {
      id: "new-root",
      label: "",
      children: [{ id: "new-local", label: "New local" }],
    };
    const loadItemChildren = vi.fn(() => oldChildren);
    const props = {
      ariaLabel: "Switching resources",
      getItemId: (item: Node) => item.id,
      getItemLabel: (item: Node) => item.label,
      getItemChildren: (item: Node) => item.children,
      getItemChildrenCount: (item: Node) => item.id === "old-remote" ? 1 : item.children?.length,
      loadItemChildren,
    };
    const { rerender } = render(<Tree rootItem={oldRoot} {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Old remote" }));
    await waitFor(() => expect(loadItemChildren).toHaveBeenCalledOnce());
    rerender(<Tree rootItem={newRoot} {...props} />);
    expect(screen.getByRole("treeitem", { name: "New local" })).toBeTruthy();

    await act(async () => {
      resolveOldChildren?.([{ id: "old-remote/stale", label: "Stale child" }]);
      await oldChildren;
    });

    expect(screen.queryByRole("treeitem", { name: "Stale child" })).toBeNull();
    expect(screen.getByRole("treeitem", { name: "New local" })).toBeTruthy();
  });

  it("keeps row actions outside the tree selection gesture", async () => {
    const onItemSelect = vi.fn();
    const onRefresh = vi.fn();

    render(
      <Tree
        rootItem={root}
        ariaLabel="Action tree"
        getItemId={(item) => item.id}
        getItemLabel={(item) => item.label}
        getItemChildren={(item) => item.children}
        renderItemActions={(item) => item.id === "src"
          ? <button type="button" onClick={onRefresh}>Refresh src</button>
          : null}
        onItemSelect={onItemSelect}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Refresh src" }));
    await waitFor(() => expect(onRefresh).toHaveBeenCalledOnce());
    expect(onItemSelect).not.toHaveBeenCalled();
  });

  it("uses Zag visible nodes with TanStack windowing for a large expanded branch", async () => {
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(320);
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(448);
    const largeRoot: Node = {
      id: "root",
      label: "",
      children: [{
        id: "catalog",
        label: "Catalog",
        children: Array.from({ length: 500 }, (_, index) => ({
          id: `catalog/table-${index + 1}`,
          label: `table_${String(index + 1).padStart(3, "0")}`,
        })),
      }],
    };
    const { container } = render(
      <Tree
        rootItem={largeRoot}
        ariaLabel="Large catalog"
        getItemId={(item) => item.id}
        getItemLabel={(item) => item.label}
        getItemChildren={(item) => item.children}
        defaultExpandedIds={["catalog"]}
      />,
    );

    expect(container.querySelector(".dbfox-tree.is-virtualized")).toBeTruthy();
    await waitFor(() => {
      const mountedRows = container.querySelectorAll(".dbfox-tree__virtual-row");
      expect(mountedRows.length).toBeGreaterThan(0);
      expect(mountedRows.length).toBeLessThan(501);
    });
    const mountedLeaf = container.querySelector('[role="treeitem"][aria-level="2"]');
    expect(mountedLeaf?.getAttribute("aria-setsize")).toBe("500");
    expect(mountedLeaf?.getAttribute("aria-posinset")).toBeTruthy();
    expect(container.querySelectorAll("[style]")).toHaveLength(0);
  });
});
