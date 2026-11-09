import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import React from "react";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { captureWorkbenchInput } from "../../resources/workbenchInput";
import {
  createStagedExtensionHost,
  initExtensionHostGlobalSdk,
} from "../extensionHost";
import { useDlcStore } from "../extensionStore";
import type { DlcModule } from "../types";

const fixturePath = resolve(
  process.cwd(),
  "../dlcs/dbfox_data/frontend/index.js",
);

async function fixtureSource() {
  // The test's data URL has no relative filesystem base. Inline the actual
  // sibling module, preserving the production module's real implementation.
  const workbook = (await readFile(resolve(fixturePath, "../workbook.js"), "utf8"))
    .replaceAll("export function ", "function ").replaceAll("export const ", "const ");
  return (await readFile(fixturePath, "utf8"))
    .replace('import { registerWorkbookPreview } from "./workbook.js";', workbook);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("dbfox.data System DLC frontend fixture", () => {
  it.each([false, true])("keeps catalog loading consistent when source changed=%s", async (sourceChanged) => {
    initExtensionHostGlobalSdk();
    const source = await fixtureSource();
    const module = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#catalog-generation-${sourceChanged}`) as DlcModule;
    let generation = 1;
    let catalogCalls = 0;
    let releaseCatalog!: (value: unknown) => void;
    const catalog = (name: string) => ({ catalog_status: "ready", tables: [{ table_id: name, qualified_name: name, columns_count: 1 }], has_more: false, next_cursor: null });
    const staged = createStagedExtensionHost("dbfox.data", { openDockTab: vi.fn(),
      invokeOperation: async <TOutput,>(_id: string, operation: string) => {
        if (operation === "profiles.list") return { profiles: [{
          profile: { id: "profile", name: "Warehouse", provider: "sqlite", status: "active", connection_generation: 1 },
          databases: [{ id: "database", display_name: "analytics", database_name: generation === 1 ? "A" : "B", status: "active", resource_generation: generation }],
        }] } as TOutput;
        if (operation === "catalog.refresh") return { status: "ready" } as TOutput;
        if (operation === "catalog.tables") {
          if (++catalogCalls === 1) return await new Promise<TOutput>(resolve => { releaseCatalog = value => resolve(value as TOutput); });
          return catalog("only_in_B") as TOutput;
        }
        throw new Error(`Unexpected operation ${operation}`);
      },
    });
    vi.stubGlobal("document", undefined);
    await module.register?.(staged.host);
    vi.unstubAllGlobals();
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    const connector = staged.getContributions().connectors[0];
    render(React.createElement(React.Fragment, null, connector.render({ projectId: "catalog-generation" })));
    await screen.findByRole("treeitem", { name: "Warehouse" });
    fireEvent.click(await screen.findByRole("button", { name: "analytics" }));
    await waitFor(() => expect(catalogCalls).toBe(1));
    generation = sourceChanged ? 2 : 1;
    await act(async () => { await connector.listResources!({ projectId: "catalog-generation" }); });
    await act(async () => { releaseCatalog(catalog("only_in_A")); });
    if (sourceChanged) {
      const branch = screen.getByRole("treeitem", { name: "analytics" });
      if (branch.getAttribute("aria-expanded") !== "true") fireEvent.click(screen.getByRole("button", { name: "analytics" }));
    }
    expect(await screen.findByRole("treeitem", { name: sourceChanged ? "only_in_B" : "only_in_A" })).toBeTruthy();
    if (sourceChanged) expect(screen.queryByRole("treeitem", { name: "only_in_A" })).toBeNull();
    expect(catalogCalls).toBe(sourceChanged ? 2 : 1);
    await module.deactivate?.();
  });

  it("does not replace a newer database generation with a late profile response", async () => {
    initExtensionHostGlobalSdk();
    const source = await fixtureSource();
    const module = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#profile-generation`) as DlcModule;
    const replies: Array<(value: unknown) => void> = [];
    const staged = createStagedExtensionHost("dbfox.data", {
      openDockTab: vi.fn(),
      invokeOperation: async <TOutput,>() => new Promise<TOutput>(resolve => {
        replies.push(value => resolve(value as TOutput));
      }),
    });
    vi.stubGlobal("document", undefined);
    await module.register?.(staged.host);
    const connector = staged.getContributions().connectors[0];
    const older = connector.listResources!({ projectId: "project-generation" });
    const newer = connector.listResources!({ projectId: "project-generation" });
    await vi.waitFor(() => expect(replies).toHaveLength(2));
    const result = (generation: number, databaseName: string) => ({ profiles: [{
      profile: { id: "profile", name: "profile", provider: "sqlite", status: "active", connection_generation: 1 },
      databases: [{ id: "database", display_name: databaseName, database_name: databaseName, status: "active", resource_generation: generation }],
    }] });
    replies[1](result(2, "B"));
    expect(await newer).toMatchObject([{ id: "database", name: "B" }]);
    replies[0](result(1, "A"));
    expect(await older).toMatchObject([{ id: "database", name: "B" }]);
    await module.deactivate?.();
  });

  it("registers the hosted Connection → Database → Table workbench", async () => {
    initExtensionHostGlobalSdk();
    vi.stubGlobal("document", undefined);
    const source = await fixtureSource();
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
    const module = await import(/* @vite-ignore */ moduleUrl) as DlcModule;
    const staged = createStagedExtensionHost("dbfox.data");

    await module.register?.(staged.host);

    const contributions = staged.getContributions();
    expect(contributions.connectors).toHaveLength(1);
    expect(contributions.connectors[0].id).toBe("dbfox.data");
    expect(contributions.connectors[0].title).toBe("数据库");
    expect(contributions.connectors[0].addLabel).toBe("新建数据库连接");
    expect(contributions.connectors[0].onAdd).toBeTypeOf("function");
    expect(contributions.dockViews.map((item) => item.viewType)).toEqual([
      "dbfox.data.workbook",
      "dbfox.data.explorer",
      "dbfox.data.catalog-table",
      "dbfox.data.sql-console",
    ]);
    expect(contributions.artifactViews.map((item) => item.id)).toEqual([
      "dbfox.data.sql",
      "dbfox.data.source-sql",
    ]);
    expect(contributions.artifactViews[0].parsePayload({
      sql: "SELECT 1",
      dialect: "sqlite",
      validationStatus: "passed",
    })).toMatchObject({
      sql: "SELECT 1",
      dialect: "sqlite",
      metadata: ["校验 passed"],
    });
  });

  it("uses the Host Tree for async catalog loading, retry, row actions, and table selection", async () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    initExtensionHostGlobalSdk();
    const source = await fixtureSource();
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#tree`;
    const module = await import(/* @vite-ignore */ moduleUrl) as DlcModule;
    const openDockTab = vi.fn();
    let catalogAttempts = 0;
    async function invokeOperation<TOutput>(_dlcId: string, operationName: string): Promise<TOutput> {
      if (operationName === "profiles.list") {
        return {
          profiles: [{
            profile: { id: "profile-1", name: "Warehouse", provider: "postgresql" },
            databases: [{
              id: "database-1",
              display_name: "analytics",
              database_name: "analytics",
            }],
          }],
        } as TOutput;
      }
      if (operationName === "catalog.tables") {
        catalogAttempts += 1;
        if (catalogAttempts === 1) throw new Error("offline");
        return {
          catalog_status: "ready",
          tables: [{
            table_id: "table-1",
            qualified_name: "public.orders",
            columns_count: 7,
          }],
          has_more: false,
          next_cursor: null,
        } as TOutput;
      }
      if (operationName === "catalog.refresh") return { status: "ready" } as TOutput;
      throw new Error(`Unexpected operation: ${operationName}`);
    }
    const staged = createStagedExtensionHost("dbfox.data", {
      invokeOperation,
      openDockTab,
    });

    vi.stubGlobal("document", undefined);
    await module.register?.(staged.host);
    vi.unstubAllGlobals();
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });

    const connector = staged.getContributions().connectors[0];
    render(React.createElement(React.Fragment, null, connector.render({ projectId: "project-tree" })));

    expect(await screen.findByRole("tree", { name: "数据库资源" })).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("treeitem", { name: "Warehouse" }).getAttribute("aria-expanded")).toBe("true"));

    fireEvent.click(screen.getByRole("button", { name: "analytics" }));
    expect(await screen.findByText("读取失败，点击重试")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "analytics" }));

    const table = await screen.findByRole("treeitem", { name: "public.orders" });
    fireEvent.click(table);
    await waitFor(() => expect(openDockTab).toHaveBeenCalledWith(
      expect.objectContaining({
        viewType: "dbfox.data.catalog-table",
        target: {
          type: "object",
          object: { kind: "dbfox.data.table", id: "table-1" },
          authority: { kind: "dbfox.data.database", id: "database-1" },
          locator: "public.orders",
        },
      }),
      true,
    ));
    const previousWorkspace = useWorkspaceStore.getState();
    const previousExtensions = useDlcStore.getState();
    try {
      previousExtensions.setProjectionResult("test", {}, staged.getContributions());
      useWorkspaceStore.setState({ activeProjectId: "project-tree", mainSurfaceByProject: {}, workbenchByConversation: {} });
      previousWorkspace.setProjectActiveConversation("project-tree", "catalog-chat");
      previousWorkspace.openDockTab(openDockTab.mock.lastCall![0]);
      expect(captureWorkbenchInput([], "catalog-chat")).toEqual([{
        label: "当前查看 · public.orders",
        object: { kind: "dbfox.data.table", id: "table-1" },
        locator: "public.orders",
      }]);
    } finally {
      useWorkspaceStore.setState(previousWorkspace);
      useDlcStore.setState(previousExtensions);
    }

    fireEvent.click(screen.getByRole("button", { name: "打开 SQL Console：analytics" }));
    expect(openDockTab).toHaveBeenCalledWith(
      expect.objectContaining({
        viewType: "dbfox.data.sql-console",
        target: {
          type: "object",
          object: { kind: "dbfox.data.database", id: "database-1" },
          authority: { kind: "dbfox.data.database", id: "database-1" },
        },
      }),
      true,
    );
    expect(catalogAttempts).toBe(2);
  });

  it("retries a failed table read locally without opening another tab", async () => {
    initExtensionHostGlobalSdk();
    const source = await fixtureSource();
    const module = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#table-retry`) as DlcModule;
    const openDockTab = vi.fn();
    let attempts = 0;
    const staged = createStagedExtensionHost("dbfox.data", { openDockTab, invokeOperation: async <TOutput,>(_id: string, operation: string) => {
      if (operation === "profiles.list") return { profiles: [{ profile: { id: "profile-retry", name: "Warehouse", provider: "postgresql" }, databases: [{ id: "db", display_name: "analytics", database_name: "analytics" }] }] } as TOutput;
      if (operation === "catalog.tables") return { catalog_status: "ready", tables: [{ table_id: "orders", qualified_name: "public.orders", columns_count: 1 }], has_more: false, next_cursor: null } as TOutput;
      if (operation === "catalog.table") {
        if (++attempts === 1) throw new Error("表结构暂时不可用。");
        return { catalog_revision: 1, columns: [{ column_name: "order_id", column_type: "bigint", is_primary_key: true }] } as TOutput;
      }
      throw new Error(`Unexpected operation: ${operation}`);
    } });
    vi.stubGlobal("document", undefined);
    await module.register?.(staged.host);
    vi.unstubAllGlobals();
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    const contribution = staged.getContributions().dockViews.find(view => view.viewType === "dbfox.data.catalog-table")!;
    render(React.createElement(React.Fragment, null, contribution.render({ viewKey: "retry-table", viewType: contribution.viewType, title: "orders", closeable: true, stateKey: "retry-table", projectId: "project-retry", target: { type: "object", object: { kind: "dbfox.data.table", id: "orders" }, authority: { kind: "dbfox.data.database", id: "db" }, locator: "public.orders" } }, { activeProjectId: "project-retry", activeConversationId: null, onAsk: vi.fn(), showToast: vi.fn(), workbenchScopeId: "retry-scope" })));
    fireEvent.click(await screen.findByRole("button", { name: "重新读取" }));
    expect(await screen.findByText("order_id")).toBeTruthy();
    const profile = await screen.findByRole("treeitem", { name: "Warehouse" });
    if (profile.getAttribute("aria-expanded") !== "true") fireEvent.click(screen.getByRole("button", { name: "Warehouse" }));
    const database = await screen.findByRole("treeitem", { name: "analytics" });
    if (database.getAttribute("aria-expanded") !== "true") fireEvent.click(screen.getByRole("button", { name: "analytics" }));
    expect(await screen.findByRole("treeitem", { name: "public.orders" })).toBeTruthy();
    expect(screen.queryByText("读取失败，点击重试")).toBeNull();
    expect(attempts).toBe(2);
    expect(openDockTab).not.toHaveBeenCalled();
  });

  it("omits a repeated database prefix in tree labels while retaining the canonical table locator", async () => {
    initExtensionHostGlobalSdk();
    const source = await fixtureSource();
    const module = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#short-label`) as DlcModule;
    const openDockTab = vi.fn();
    const staged = createStagedExtensionHost("dbfox.data", { openDockTab, invokeOperation: async <TOutput,>(_id: string, operation: string) => {
      if (operation === "profiles.list") return { profiles: [{ profile: { id: "mysql-profile", name: "Warehouse", provider: "mysql" }, databases: [{ id: "mysql-db", display_name: "creatorhub", database_name: "creatorhub" }] }] } as TOutput;
      if (operation === "catalog.tables") return { catalog_status: "ready", tables: [{ table_id: "orders", qualified_name: "creatorhub.orders", columns_count: 4 }], has_more: false, next_cursor: null } as TOutput;
      throw new Error(`Unexpected operation: ${operation}`);
    } });
    vi.stubGlobal("document", undefined);
    await module.register?.(staged.host);
    vi.unstubAllGlobals();
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    render(React.createElement(React.Fragment, null, staged.getContributions().connectors[0].render({ projectId: "short-label" })));
    const profile = await screen.findByRole("treeitem", { name: "Warehouse" });
    await waitFor(() => expect(profile.getAttribute("aria-expanded")).toBe("true"));
    fireEvent.click(screen.getByRole("button", { name: "creatorhub" }));
    fireEvent.click(await screen.findByRole("treeitem", { name: "orders" }));
    await waitFor(() => expect(openDockTab).toHaveBeenCalledWith(expect.objectContaining({ target: expect.objectContaining({ locator: "creatorhub.orders" }) }), true));
  });
});
