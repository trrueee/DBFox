import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import React from "react";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createStagedExtensionHost,
  initExtensionHostGlobalSdk,
} from "../extensionHost";
import type { DlcModule } from "../types";

const fixturePath = resolve(
  process.cwd(),
  "../dlcs/dbfox_data/frontend/index.js",
);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("dbfox.data System DLC frontend fixture", () => {
  it("registers the hosted Connection → Database → Table workbench", async () => {
    initExtensionHostGlobalSdk();
    vi.stubGlobal("document", undefined);
    const source = await readFile(fixturePath, "utf8");
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
    const module = await import(/* @vite-ignore */ moduleUrl) as DlcModule;
    const staged = createStagedExtensionHost("dbfox.data");

    await module.register?.(staged.host);

    const contributions = staged.getContributions();
    expect(contributions.connectors).toHaveLength(1);
    expect(contributions.connectors[0].id).toBe("dbfox.data");
    expect(contributions.connectors[0].title).toBe("数据");
    expect(contributions.connectors[0].addLabel).toBe("新建数据库连接");
    expect(contributions.connectors[0].onAdd).toBeTypeOf("function");
    expect(contributions.dockViews.map((item) => item.viewType)).toEqual([
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
    initExtensionHostGlobalSdk();
    const source = await readFile(fixturePath, "utf8");
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

    const connector = staged.getContributions().connectors[0];
    render(React.createElement(React.Fragment, null, connector.render({ projectId: "project-tree" })));

    expect(await screen.findByRole("tree", { name: "数据库资源" })).toBeTruthy();
    expect(screen.getByRole("treeitem", { name: "Warehouse" }).getAttribute("aria-expanded")).toBe("true");

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
});
