import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = resolve(here, "..");

function read(relativePath: string) {
  return readFileSync(resolve(srcRoot, relativePath), "utf8");
}

describe("SQL Console tab state isolation", () => {
  it("stores sqlConsoleState as Record<string, SqlConsoleTabState> keyed by tab ID", () => {
    const tabsHook = read("stores/workspaceStore.ts");

    expect(tabsHook).toMatch(/sqlConsoleState.*Record<string,\s*SqlConsoleTabState>/);
    expect(tabsHook).toContain("Record<string, SqlConsoleTabState>");
  });

  it("does not use a single shared sqlQuery state", () => {
    const app = read("App.tsx");

    expect(app).not.toMatch(/useState.*sqlQuery/);
    expect(app).not.toMatch(/setSqlQuery/);
  });

  it("initializes per-tab state in openSqlConsole with defaultSql draft", () => {
    const tabsHook = read("stores/workspaceStore.ts");

    expect(tabsHook).toMatch(/openSqlConsole.*initialSql/);
    expect(tabsHook).toContain("sqlConsoleState");
    expect(tabsHook).toMatch(/draftSql:\s*initialSql \?\? defaultSql/);
  });

  it("cleans up sqlConsoleState entry when closing a SQL tab", () => {
    const tabsHook = read("stores/workspaceStore.ts");

    expect(tabsHook).toMatch(/closeTab[\s\S]*sqlConsoleState/);
    expect(tabsHook).toContain("const { [tabId]: _, ...rest }");
  });

  it("passes tabId and tab-scoped state to SqlConsoleWorkspace", () => {
    const router = read("features/appShell/WorkspaceRouter.tsx");

    expect(router).toContain("tabId={activeTab.id}");
    expect(router).toContain("state={tabState}");
    expect(router).toContain("onPatchState");
    expect(router).toContain("onAppendEntries");
  });

  it("SqlConsoleWorkspace receives tab-scoped props instead of shared sqlQuery", () => {
    const ws = read("features/workspace/SqlConsoleWorkspace.tsx");

    expect(ws).toContain("tabId: string");
    expect(ws).toContain("state: SqlConsoleTabState");
    expect(ws).toContain("onPatchState");
    expect(ws).toContain("onAppendEntries");
    expect(ws).not.toMatch(/interface.*sqlQuery/);
    expect(ws).not.toMatch(/onSqlQueryChange/);
  });

  it("SqlConsoleWorkspace uses onPatchState for draft changes and running flag", () => {
    const ws = read("features/workspace/SqlConsoleWorkspace.tsx");

    expect(ws).toContain("onPatchState(tabId, { draftSql:");
    expect(ws).toContain("onPatchState(tabId, { running: true })");
    expect(ws).toContain("onPatchState(tabId, { running: false })");
  });

  it("exports SqlConsoleTabState type for use in App.tsx", () => {
    const ws = read("features/workspace/SqlConsoleWorkspace.tsx");

    expect(ws).toContain("export type SqlConsoleTabState");
  });

  it("no component uses local useState for console entries", () => {
    const ws = read("features/workspace/SqlConsoleWorkspace.tsx");

    expect(ws).not.toMatch(/useState<ConsoleEntry\[\]>/);
    expect(ws).not.toMatch(/useState\(false\).*running/);
  });

  it("onSetSqlQuery has been removed from the prop chain", () => {
    const ws = read("features/workspace/SqlConsoleWorkspace.tsx");
    const queryResult = read("features/workspace/QueryResultWorkspace.tsx");
    const taskView = read("features/agentTask/AgentTaskView.tsx");
    const turnItem = read("features/agentTask/AgentTurnItem.tsx");
    const finalAnswer = read("features/agentTask/FinalAnswerCard.tsx");
    const artifactRenderer = read("features/workspace/artifacts/ArtifactRenderer.tsx");
    const sqlArtifact = read("features/workspace/artifacts/SqlArtifactView.tsx");

    expect(ws).not.toContain("onSetSqlQuery");
    expect(queryResult).not.toContain("onSetSqlQuery");
    expect(taskView).not.toContain("onSetSqlQuery");
    expect(turnItem).not.toContain("onSetSqlQuery");
    expect(finalAnswer).not.toContain("onSetSqlQuery");
    expect(artifactRenderer).not.toContain("onSetSqlQuery");
    expect(sqlArtifact).not.toContain("onSetSqlQuery");
  });

  it("openSqlConsole accepts optional initialSql parameter", () => {
    const tabsHook = read("stores/workspaceStore.ts");

    expect(tabsHook).toMatch(/openSqlConsole:\s*\(initialSql/);
  });

  it("ContextDrawer onGenerateIndexSql passes SQL directly to openSqlConsole", () => {
    const app = read("App.tsx");

    expect(app).toContain("openSqlConsole(\"ALTER TABLE comment_infos ADD INDEX idx_user_id (user_id);\")");
  });
});
