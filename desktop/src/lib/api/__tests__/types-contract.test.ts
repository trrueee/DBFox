import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const legacyTypesSource = () => readFileSync(resolve(__dirname, "../types.ts"), "utf8");
const groupedTypesSource = (fileName: string) => readFileSync(resolve(__dirname, "../types", fileName), "utf8");
const workspaceSource = (path: string) => readFileSync(resolve(process.cwd(), path), "utf8");

describe("api type contracts", () => {
  it("keeps the legacy types module as a compatibility barrel", () => {
    expect(legacyTypesSource().trim()).toBe('export * from "./types/index";');
  });

  it("keeps SchemaSyncResult as a closed response shape", () => {
    const source = groupedTypesSource("datasource.ts");
    const match = source.match(/export interface SchemaSyncResult \{([\s\S]*?)\n\}/);
    expect(match?.[1]).toBeTruthy();
    expect(match?.[1]).not.toContain("[key: string]");
    expect(match?.[1]).toContain("tablesDropped?: number");
    expect(match?.[1]).toContain("columnsCreated?: number");
    expect(match?.[1]).toContain("columnsUpdated?: number");
    expect(match?.[1]).toContain("columnsRemoved?: number");
  });

  it("models nullable datasource connection fields returned by the backend", () => {
    const source = groupedTypesSource("datasource.ts");
    expect(source).toContain("host: string | null;");
    expect(source).toContain("username: string | null;");
  });

  it("uses a discriminated artifact payload union instead of a bare record", () => {
    const source = groupedTypesSource("artifact.ts");
    expect(source).toContain("export type AgentArtifactPayload =");
    expect(source).toContain("payload: AgentArtifactPayload;");
    expect(source).not.toContain("payload: Record<string, unknown>;");
  });

  it("does not expose rows-returning query execution clients in the desktop app", () => {
    const queryClient = workspaceSource("src/lib/api/query.ts");
    const engineApi = workspaceSource("src/features/engine/engineApi.ts");
    const queryTypes = groupedTypesSource("query.ts");

    expect(queryClient).not.toContain("/query/execute");
    expect(queryClient).not.toContain("executeSql");
    expect(engineApi).not.toContain("executeSql");
    expect(engineApi).not.toContain("EngineSqlResult");
    expect(queryTypes).not.toContain("export interface QueryResult");
    expect(existsSync(resolve(process.cwd(), "src/components/ConsoleTranscript.tsx"))).toBe(false);
  });
});
