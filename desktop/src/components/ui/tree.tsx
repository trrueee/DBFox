import { useEffect, useId, useInsertionEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { useVirtualizer, type Virtualizer } from "@tanstack/react-virtual";
import { normalizeProps, useMachine } from "@zag-js/react";
import * as treeView from "@zag-js/tree-view";
import { clearCspVirtualLayout, setCspVirtualLayout } from "../../lib/cspVirtualLayout";
import "./tree.css";

const VIRTUALIZE_AFTER_VISIBLE_NODES = 100;
const VIRTUAL_TREE_ROW_ESTIMATE_PX = 30;

export interface TreeItemRenderState {
  expanded: boolean;
  focused: boolean;
  selected: boolean;
  branch: boolean;
  loading: boolean;
  loadError?: Error;
}

export interface TreeProps<T> {
  rootItem: T;
  ariaLabel: string;
  getItemId(item: T): string;
  getItemLabel(item: T): string;
  getItemChildren(item: T): readonly T[] | undefined;
  getItemChildrenCount?: (item: T) => number | undefined;
  loadItemChildren?: (item: T, signal: AbortSignal) => Promise<readonly T[]>;
  renderItemIcon?: (item: T, state: TreeItemRenderState) => ReactNode;
  renderItemMeta?: (item: T, state: TreeItemRenderState) => ReactNode;
  renderItemActions?: (item: T, state: TreeItemRenderState) => ReactNode;
  renderBranchFooter?: (item: T, state: TreeItemRenderState) => ReactNode;
  defaultExpandedIds?: readonly string[];
  onExpandedIdsChange?: (ids: readonly string[]) => void;
  selectedIds?: readonly string[];
  onSelectedIdsChange?: (ids: readonly string[], items: readonly T[]) => void;
  onItemSelect?: (item: T) => void;
  className?: string;
}

/**
 * Versioned Host tree primitive for package-free DLC frontends.
 * Zag owns keyboard, focus, selection, typeahead, and expansion behavior.
 * DBFox owns DOM/CSS so the component does not depend on ad-hoc inline layout styles.
 */
export function Tree<T>({
  rootItem,
  ariaLabel,
  getItemId,
  getItemLabel,
  getItemChildren,
  getItemChildrenCount,
  loadItemChildren,
  renderItemIcon,
  renderItemMeta,
  renderItemActions,
  renderBranchFooter,
  defaultExpandedIds = [],
  onExpandedIdsChange,
  selectedIds,
  onSelectedIdsChange,
  onItemSelect,
  className,
}: TreeProps<T>) {
  const id = useId();
  const virtualLayoutId = `tree-${id.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizerRef = useRef<Virtualizer<HTMLDivElement, Element> | null>(null);
  const nodeRowIndexesRef = useRef<readonly number[]>([]);
  const deferredFocusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentRootRef = useRef(rootItem);
  currentRootRef.current = rootItem;
  const baseCollection = useMemo(
    () => treeView.collection<T>({
      rootNode: rootItem,
      nodeToValue: getItemId,
      nodeToString: getItemLabel,
      nodeToChildren: (item) => [...(getItemChildren(item) ?? [])],
      ...(getItemChildrenCount ? { nodeToChildrenCount: getItemChildrenCount } : {}),
    }),
    [getItemChildren, getItemChildrenCount, getItemId, getItemLabel, rootItem],
  );
  const [loadedCollection, setLoadedCollection] = useState<{
    rootItem: T;
    collection: typeof baseCollection;
  } | null>(null);
  const [loadErrorState, setLoadErrorState] = useState<{
    rootItem: T;
    errors: ReadonlyMap<string, Error>;
  }>(() => ({ rootItem, errors: new Map() }));
  const loadErrors = loadErrorState.rootItem === rootItem
    ? loadErrorState.errors
    : new Map<string, Error>();
  const collection = loadedCollection?.rootItem === rootItem
    ? loadedCollection.collection
    : baseCollection;
  const service = useMachine(treeView.machine, {
    id,
    collection,
    defaultExpandedValue: [...defaultExpandedIds],
    ...(selectedIds ? { selectedValue: [...selectedIds] } : {}),
    selectionMode: "single",
    expandOnClick: true,
    translations: { treeLabel: ariaLabel },
    scrollToIndexFn(details) {
      const rowIndex = nodeRowIndexesRef.current[details.index] ?? details.index;
      virtualizerRef.current?.scrollToIndex(rowIndex, { align: "auto" });
      if (deferredFocusTimerRef.current) clearTimeout(deferredFocusTimerRef.current);
      deferredFocusTimerRef.current = setTimeout(() => {
        details.getElement()?.focus({ preventScroll: true });
        deferredFocusTimerRef.current = null;
      }, 50);
    },
    ...(loadItemChildren ? {
      loadChildren: async (details: treeView.LoadChildrenDetails<T>) => {
        const value = getItemId(details.node);
        setLoadErrorState((previousState) => {
          const previous = previousState.rootItem === rootItem
            ? previousState.errors
            : new Map<string, Error>();
          if (!previous.has(value)) return { rootItem, errors: previous };
          const next = new Map(previous);
          next.delete(value);
          return { rootItem, errors: next };
        });
        const requestRoot = rootItem;
        const children = [...await loadItemChildren(details.node, details.signal)];
        if (details.signal.aborted || currentRootRef.current !== requestRoot) {
          throw new DOMException("Tree root changed while children were loading", "AbortError");
        }
        return children;
      },
      onLoadChildrenComplete(details: treeView.LoadChildrenCompleteDetails<T>) {
        if (getItemId(details.collection.rootNode) !== getItemId(rootItem)) return;
        setLoadedCollection({ rootItem, collection: details.collection });
      },
      onLoadChildrenError(details: treeView.LoadChildrenErrorDetails<T>) {
        const currentFailures = details.nodes.filter(
          (failed) => baseCollection.findNode(getItemId(failed.node)) === failed.node,
        );
        if (currentFailures.length === 0) return;
        setLoadErrorState((previousState) => {
          const previous = previousState.rootItem === rootItem
            ? previousState.errors
            : new Map<string, Error>();
          const next = new Map(previous);
          for (const failed of currentFailures) {
            next.set(getItemId(failed.node), failed.error);
          }
          return { rootItem, errors: next };
        });
      },
    } : {}),
    onExpandedChange(details) {
      onExpandedIdsChange?.(details.expandedValue);
    },
    onSelectionChange(details) {
      onSelectedIdsChange?.(details.selectedValue, details.selectedNodes as T[]);
      const selectedItem = (details.selectedNodes as T[]).at(-1);
      if (selectedItem) onItemSelect?.(selectedItem);
    },
  });
  const api = treeView.connect(service, normalizeProps);
  const collectionRoot = api.collection.rootNode as T;
  const rootChildren = api.collection.getNodeChildren(collectionRoot) as T[];
  const visibleNodes = api.getVisibleNodes() as Array<{ node: T; indexPath: number[] }>;
  const virtualRows = buildVirtualRows({
    visibleNodes,
    api,
    getItemId,
    loadErrors,
    renderBranchFooter,
  });
  nodeRowIndexesRef.current = virtualRows.nodeRowIndexes;
  const shouldVirtualize = visibleNodes.length > VIRTUALIZE_AFTER_VISIBLE_NODES;

  // TanStack Virtual provides the official windowing runtime; Zag remains the
  // only owner of tree focus, keyboard, expansion, and selection state.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: virtualRows.rows.length,
    enabled: shouldVirtualize,
    getScrollElement: () => scrollRef.current,
    getItemKey: (index) => virtualRows.rows[index]?.key ?? index,
    estimateSize: () => VIRTUAL_TREE_ROW_ESTIMATE_PX,
    overscan: 8,
    initialRect: { width: 320, height: 448 },
    useFlushSync: false,
  });
  virtualizerRef.current = virtualizer;
  const virtualItems = virtualizer.getVirtualItems();

  useEffect(() => () => {
    if (deferredFocusTimerRef.current) clearTimeout(deferredFocusTimerRef.current);
  }, []);

  useInsertionEffect(() => {
    if (!shouldVirtualize) {
      clearCspVirtualLayout(virtualLayoutId);
      return;
    }
    setCspVirtualLayout(
      virtualLayoutId,
      virtualizer.getTotalSize(),
      virtualItems.map((item) => ({ index: item.index, start: item.start })),
      "tree",
    );
    return () => clearCspVirtualLayout(virtualLayoutId);
  }, [shouldVirtualize, virtualItems, virtualLayoutId, virtualizer]);

  return (
    <div
      {...api.getRootProps()}
      ref={scrollRef}
      className={joinClassNames("dbfox-tree", shouldVirtualize ? "is-virtualized" : undefined, className)}
    >
      <div
        {...api.getTreeProps()}
        aria-label={ariaLabel}
        aria-labelledby={undefined}
        className={shouldVirtualize ? "dbfox-tree__virtual-canvas" : undefined}
        data-virtual-layout={shouldVirtualize ? virtualLayoutId : undefined}
      >
        {shouldVirtualize
          ? virtualItems.map((virtualItem) => {
              const row = virtualRows.rows[virtualItem.index];
              return (
                <div
                  key={row.key}
                  ref={virtualizer.measureElement}
                  className="dbfox-tree__virtual-row"
                  data-index={virtualItem.index}
                  data-virtual-layout={virtualLayoutId}
                >
                  {row.type === "node" ? (
                    <TreeFlatNode
                      item={row.item}
                      indexPath={row.indexPath}
                      api={api}
                      getItemId={getItemId}
                      getItemLabel={getItemLabel}
                      loadErrors={loadErrors}
                      renderItemIcon={renderItemIcon}
                      renderItemMeta={renderItemMeta}
                      renderItemActions={renderItemActions}
                    />
                  ) : (
                    <div
                      className={joinClassNames(
                        "dbfox-tree__branch-footer",
                        virtualDepthClass(row.indexPath.length + 1),
                      )}
                      onClick={(event) => event.stopPropagation()}
                      onKeyDown={(event) => event.stopPropagation()}
                    >
                      {row.content}
                    </div>
                  )}
                </div>
              );
            })
          : rootChildren.map((item, index) => (
              <TreeNode
                key={getItemId(item)}
                item={item}
                indexPath={[index]}
                api={api}
                getItemId={getItemId}
                getItemLabel={getItemLabel}
                getItemChildren={getItemChildren}
                loadErrors={loadErrors}
                renderItemIcon={renderItemIcon}
                renderItemMeta={renderItemMeta}
                renderItemActions={renderItemActions}
                renderBranchFooter={renderBranchFooter}
              />
            ))}
      </div>
    </div>
  );
}

type VirtualTreeRow<T> =
  | { type: "node"; key: string; item: T; indexPath: number[] }
  | { type: "footer"; key: string; indexPath: number[]; content: ReactNode };

function buildVirtualRows<T>({
  visibleNodes,
  api,
  getItemId,
  loadErrors,
  renderBranchFooter,
}: {
  visibleNodes: Array<{ node: T; indexPath: number[] }>;
  api: treeView.Api;
  getItemId(item: T): string;
  loadErrors: ReadonlyMap<string, Error>;
  renderBranchFooter?: (item: T, state: TreeItemRenderState) => ReactNode;
}): { rows: VirtualTreeRow<T>[]; nodeRowIndexes: number[] } {
  const rows: VirtualTreeRow<T>[] = [];
  const nodeRowIndexes: number[] = [];
  const openBranches: Array<{
    item: T;
    indexPath: number[];
    content: ReactNode;
  }> = [];

  const closeBranchesAtOrBelow = (depth: number) => {
    while ((openBranches.at(-1)?.indexPath.length ?? -1) >= depth) {
      const branch = openBranches.pop();
      if (!branch || branch.content == null) continue;
      rows.push({
        type: "footer",
        key: `${getItemId(branch.item)}:footer`,
        indexPath: branch.indexPath,
        content: branch.content,
      });
    }
  };

  for (const entry of visibleNodes) {
    closeBranchesAtOrBelow(entry.indexPath.length);
    nodeRowIndexes.push(rows.length);
    rows.push({
      type: "node",
      key: getItemId(entry.node),
      item: entry.node,
      indexPath: entry.indexPath,
    });
    const nodeState = api.getNodeState(entry);
    if (nodeState.isBranch && nodeState.expanded) {
      const state = treeItemRenderState(entry.node, nodeState, getItemId, loadErrors);
      openBranches.push({
        item: entry.node,
        indexPath: entry.indexPath,
        content: renderBranchFooter?.(entry.node, state),
      });
    }
  }
  closeBranchesAtOrBelow(0);
  return { rows, nodeRowIndexes };
}

function TreeFlatNode<T>({
  item,
  indexPath,
  api,
  getItemId,
  getItemLabel,
  loadErrors,
  renderItemIcon,
  renderItemMeta,
  renderItemActions,
}: {
  item: T;
  indexPath: number[];
  api: treeView.Api;
  getItemId(item: T): string;
  getItemLabel(item: T): string;
  loadErrors: ReadonlyMap<string, Error>;
  renderItemIcon?: (item: T, state: TreeItemRenderState) => ReactNode;
  renderItemMeta?: (item: T, state: TreeItemRenderState) => ReactNode;
  renderItemActions?: (item: T, state: TreeItemRenderState) => ReactNode;
}) {
  const nodeProps = { node: item, indexPath };
  const nodeState = api.getNodeState(nodeProps);
  const state = treeItemRenderState(item, nodeState, getItemId, loadErrors);
  const label = getItemLabel(item);
  const icon = renderItemIcon?.(item, state);
  const meta = renderItemMeta?.(item, state);
  const actions = renderItemActions?.(item, state);
  const siblingCount = (api.collection.getSiblingNodes(indexPath) as T[]).length;
  const declaredTreePosition = {
    "aria-posinset": (indexPath.at(-1) ?? 0) + 1,
    "aria-setsize": siblingCount,
  };
  const depthClass = virtualDepthClass(indexPath.length);

  if (nodeState.isBranch) {
    const branchProps = withoutInlineStyle(api.getBranchProps(nodeProps));
    return (
      <div {...branchProps} {...declaredTreePosition} aria-label={label} className={depthClass}>
        <div className="dbfox-tree__row-shell">
          <div {...api.getBranchControlProps(nodeProps)} aria-label={label} className="dbfox-tree__row dbfox-tree__branch-row">
            <span {...api.getBranchIndicatorProps(nodeProps)} className="dbfox-tree__indicator">
              <ChevronRight aria-hidden="true" />
            </span>
            {icon != null && <span className="dbfox-tree__icon">{icon}</span>}
            <span {...api.getBranchTextProps(nodeProps)} className="dbfox-tree__label" title={label}>{label}</span>
            {meta != null && <span className="dbfox-tree__meta">{meta}</span>}
          </div>
          {actions != null && <TreeNodeActions>{actions}</TreeNodeActions>}
        </div>
      </div>
    );
  }

  const itemProps = withoutInlineStyle(api.getItemProps(nodeProps));
  return (
    <div
      {...itemProps}
      {...declaredTreePosition}
      aria-label={label}
      className={joinClassNames("dbfox-tree__row-shell", "dbfox-tree__item-shell", depthClass)}
    >
      <div className="dbfox-tree__row dbfox-tree__item-row">
        <span className="dbfox-tree__indicator dbfox-tree__indicator--leaf" aria-hidden="true" />
        {icon != null && <span className="dbfox-tree__icon">{icon}</span>}
        <span {...api.getItemTextProps(nodeProps)} className="dbfox-tree__label" title={label}>{label}</span>
        {meta != null && <span className="dbfox-tree__meta">{meta}</span>}
      </div>
      {actions != null && <TreeNodeActions>{actions}</TreeNodeActions>}
    </div>
  );
}

function treeItemRenderState<T>(
  item: T,
  nodeState: ReturnType<treeView.Api["getNodeState"]>,
  getItemId: (item: T) => string,
  loadErrors: ReadonlyMap<string, Error>,
): TreeItemRenderState {
  return {
    expanded: nodeState.expanded,
    focused: nodeState.focused,
    selected: nodeState.selected,
    branch: nodeState.isBranch,
    loading: nodeState.loading,
    loadError: loadErrors.get(getItemId(item)),
  };
}

function virtualDepthClass(depth: number): string {
  return `dbfox-tree__virtual-depth-${Math.min(Math.max(depth, 1), 8)}`;
}

function TreeNode<T>({
  item,
  indexPath,
  api,
  getItemId,
  getItemLabel,
  getItemChildren,
  loadErrors,
  renderItemIcon,
  renderItemMeta,
  renderItemActions,
  renderBranchFooter,
}: {
  item: T;
  indexPath: number[];
  api: treeView.Api;
  getItemId(item: T): string;
  getItemLabel(item: T): string;
  getItemChildren(item: T): readonly T[] | undefined;
  loadErrors: ReadonlyMap<string, Error>;
  renderItemIcon?: (item: T, state: TreeItemRenderState) => ReactNode;
  renderItemMeta?: (item: T, state: TreeItemRenderState) => ReactNode;
  renderItemActions?: (item: T, state: TreeItemRenderState) => ReactNode;
  renderBranchFooter?: (item: T, state: TreeItemRenderState) => ReactNode;
}) {
  const nodeProps = { node: item, indexPath };
  const nodeState = api.getNodeState(nodeProps);
  const state: TreeItemRenderState = {
    expanded: nodeState.expanded,
    focused: nodeState.focused,
    selected: nodeState.selected,
    branch: nodeState.isBranch,
    loading: nodeState.loading,
    loadError: loadErrors.get(getItemId(item)),
  };
  const label = getItemLabel(item);
  const icon = renderItemIcon?.(item, state);
  const meta = renderItemMeta?.(item, state);
  const actions = renderItemActions?.(item, state);
  const branchFooter = renderBranchFooter?.(item, state);
  const children = api.collection.getNodeChildren(item) as T[];

  if (nodeState.isBranch) {
    const branchProps = withoutInlineStyle(api.getBranchProps(nodeProps));
    return (
      <div {...branchProps} aria-label={label}>
        <div className="dbfox-tree__row-shell">
          <div {...api.getBranchControlProps(nodeProps)} aria-label={label} className="dbfox-tree__row dbfox-tree__branch-row">
            <span {...api.getBranchIndicatorProps(nodeProps)} className="dbfox-tree__indicator">
              <ChevronRight aria-hidden="true" />
            </span>
            {icon != null && <span className="dbfox-tree__icon">{icon}</span>}
            <span {...api.getBranchTextProps(nodeProps)} className="dbfox-tree__label" title={label}>
              {label}
            </span>
            {meta != null && <span className="dbfox-tree__meta">{meta}</span>}
          </div>
          {actions != null && <TreeNodeActions>{actions}</TreeNodeActions>}
        </div>
        <div {...api.getBranchContentProps(nodeProps)} className="dbfox-tree__group">
          {children.map((child, index) => (
            <TreeNode
              key={getItemId(child)}
              item={child}
              indexPath={[...indexPath, index]}
              api={api}
              getItemId={getItemId}
              getItemLabel={getItemLabel}
              getItemChildren={getItemChildren}
              loadErrors={loadErrors}
              renderItemIcon={renderItemIcon}
              renderItemMeta={renderItemMeta}
              renderItemActions={renderItemActions}
              renderBranchFooter={renderBranchFooter}
            />
          ))}
          {branchFooter != null && (
            <div
              className="dbfox-tree__branch-footer"
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => event.stopPropagation()}
            >
              {branchFooter}
            </div>
          )}
        </div>
      </div>
    );
  }

  const itemProps = withoutInlineStyle(api.getItemProps(nodeProps));
  return (
    <div {...itemProps} aria-label={label} className="dbfox-tree__row-shell dbfox-tree__item-shell">
      <div className="dbfox-tree__row dbfox-tree__item-row">
        <span className="dbfox-tree__indicator dbfox-tree__indicator--leaf" aria-hidden="true" />
        {icon != null && <span className="dbfox-tree__icon">{icon}</span>}
        <span {...api.getItemTextProps(nodeProps)} className="dbfox-tree__label" title={label}>
          {label}
        </span>
        {meta != null && <span className="dbfox-tree__meta">{meta}</span>}
      </div>
      {actions != null && <TreeNodeActions>{actions}</TreeNodeActions>}
    </div>
  );
}

function TreeNodeActions({ children }: { children: ReactNode }) {
  return (
    <div
      className="dbfox-tree__actions"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      {children}
    </div>
  );
}

function withoutInlineStyle<T extends { style?: unknown }>(props: T): Omit<T, "style"> {
  const safeProps = { ...props };
  delete safeProps.style;
  return safeProps;
}

function joinClassNames(...names: Array<string | undefined>) {
  return names.filter(Boolean).join(" ");
}
