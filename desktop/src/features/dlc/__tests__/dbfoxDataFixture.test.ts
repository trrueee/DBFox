import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

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
  });
});
