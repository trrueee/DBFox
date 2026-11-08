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
  it("loads default-expanded lazy ancestors through Zag and keeps selection visible", async () => {
    const nestedRoot = { id: "root", label: "", children: [{ id: "src", label: "src" }] };
    const loadItemChildren = vi.fn(async (node: Node) => node.id === "src"
      ? [{ id: "src/lib", label: "lib" }] : [{ id: "src/lib/main.py", label: "main.py" }]);
    render(<Tree rootItem={nestedRoot} ariaLabel="Nested files"
      getItemId={(node: Node) => node.id} getItemLabel={(node: Node) => node.label}
      getItemChildren={(node: Node) => node.children}
      getItemChildrenCount={(node: Node) => node.id.endsWith(".py") ? undefined : 1}
      loadItemChildren={loadItemChildren} defaultExpandedIds={["src", "src/lib"]}
      selectedIds={["src/lib/main.py"]} />);
    expect((await screen.findByRole("treeitem", { name: "main.py" })).getAttribute("aria-selected")).toBe("true");
    expect(loadItemChildren).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "src" }));
    await waitFor(() => expect(screen.queryByRole("treeitem", { name: "main.py" })).toBeNull());
    expect(loadItemChildren).toHaveBeenCalledTimes(2);
  });
  it.each([2, 150])("reactivates a selected leaf after its tab closes (%i visible nodes)", async (count) => {
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(320);
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(448);
    const items = Array.from({ length: count }, (_, index) => ({ id: `world-${index}`, label: `World ${index}` }));
    const onItemSelect = vi.fn();
    const onSelectedIdsChange = vi.fn();
    const onAction = vi.fn();
    render(<Tree
      rootItem={{ id: "root", label: "", children: items }}
      ariaLabel="Worlds"
      getItemId={(item: Node) => item.id}
      getItemLabel={(item: Node) => item.label}
      getItemChildren={(item: Node) => item.children}
      onItemSelect={onItemSelect}
      onSelectedIdsChange={onSelectedIdsChange}
      renderItemActions={(item) => <button type="button" onClick={onAction}>Inspect {item.label}</button>}
    />);
    const leaf = await screen.findByRole("treeitem", { name: "World 0" });
    fireEvent.click(leaf);
    await waitFor(() => expect(onItemSelect).toHaveBeenCalledTimes(1));
    expect(onSelectedIdsChange).toHaveBeenCalledTimes(1);
    // The tab closes independently; the resource selection remains in the tree.
    fireEvent.click(leaf);
    await waitFor(() => expect(onItemSelect).toHaveBeenCalledTimes(2));
    fireEvent.keyDown(leaf, { key: "Enter" });
    await waitFor(() => expect(onItemSelect).toHaveBeenCalledTimes(3));
    expect(onItemSelect.mock.calls.every(([item]) => item === items[0])).toBe(true);
    expect(onSelectedIdsChange).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Inspect World 0" }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Inspect World 0" }), { key: "Enter" });
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onItemSelect).toHaveBeenCalledTimes(3);
  });

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

  it("mounts only visible rows when a 10,000-node branch is collapsed and reopened", async () => {
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(320);
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(448);
    const largeRoot: Node = {
      id: "root", label: "", children: [{
        id: "scene", label: "Scene",
        children: Array.from({ length: 9_999 }, (_, index) => ({
          id: `object-${index}`, label: `Object ${index}`,
        })),
      }],
    };
    const renderItemIcon = vi.fn(() => null);
    const { container } = render(<Tree
      rootItem={largeRoot}
      ariaLabel="Scene hierarchy"
      getItemId={(item) => item.id}
      getItemLabel={(item) => item.label}
      getItemChildren={(item) => item.children}
      renderItemIcon={renderItemIcon}
    />);
    expect(container.querySelectorAll('[role="treeitem"]')).toHaveLength(1);
    expect(renderItemIcon.mock.calls.length).toBeLessThan(10);
    fireEvent.click(screen.getByRole("button", { name: "Scene" }));
    await waitFor(() => {
      expect(container.querySelector(".is-virtualized")).toBeTruthy();
      const rows = container.querySelectorAll('[role="treeitem"]');
      expect(rows.length).toBeGreaterThan(1);
      expect(rows.length).toBeLessThan(80);
    });
    fireEvent.click(screen.getByRole("button", { name: "Scene" }));
    await waitFor(() => expect(container.querySelectorAll('[role="treeitem"]')).toHaveLength(1));
    expect(container.querySelector(".is-virtualized")).toBeNull();
    expect(container.querySelectorAll("[style]")).toHaveLength(0);
  });

  it("retains nested expansion and controlled selection while collapsed children unmount", async () => {
    const nestedRoot: Node = { id: "root", label: "", children: [{
      id: "scene", label: "Scene", children: [{
        id: "group", label: "Group", children: [{ id: "cube", label: "Cube" }],
      }],
    }] };
    const { container } = render(<Tree
      rootItem={nestedRoot}
      ariaLabel="Nested hierarchy"
      getItemId={(item) => item.id}
      getItemLabel={(item) => item.label}
      getItemChildren={(item) => item.children}
      defaultExpandedIds={["scene", "group"]}
      selectedIds={["cube"]}
      renderBranchFooter={(item) => item.id === "group" ? "Group footer" : null}
    />);
    const branch = screen.getByRole("button", { name: "Scene" });
    act(() => { branch.focus(); });
    fireEvent.keyDown(branch, { key: "ArrowLeft" });
    await waitFor(() => expect(container.querySelectorAll('[role="treeitem"]')).toHaveLength(1));
    expect(screen.queryByText("Group footer")).toBeNull();
    expect(document.activeElement).toBe(branch);
    fireEvent.keyDown(branch, { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByRole("treeitem", { name: "Cube" }).getAttribute("aria-selected")).toBe("true"));
    expect(screen.getByText("Group footer")).toBeTruthy();
    fireEvent.keyDown(branch, { key: "ArrowRight" });
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Group" })));
  });
});
