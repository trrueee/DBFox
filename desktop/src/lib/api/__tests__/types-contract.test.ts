import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const typesSource = () => readFileSync(resolve(__dirname, "../types.ts"), "utf8");

describe("api type contracts", () => {
  it("keeps SchemaSyncResult as a closed response shape", () => {
    const source = typesSource();
    const match = source.match(/export interface SchemaSyncResult \{([\s\S]*?)\n\}/);
    expect(match?.[1]).toBeTruthy();
    expect(match?.[1]).not.toContain("[key: string]");
    expect(match?.[1]).toContain("tablesDropped?: number");
    expect(match?.[1]).toContain("columnsCreated?: number");
    expect(match?.[1]).toContain("columnsUpdated?: number");
    expect(match?.[1]).toContain("columnsRemoved?: number");
  });

  it("models nullable datasource connection fields returned by the backend", () => {
    const source = typesSource();
    expect(source).toContain("host: string | null;");
    expect(source).toContain("username: string | null;");
  });

  it("uses a discriminated artifact payload union instead of a bare record", () => {
    const source = typesSource();
    expect(source).toContain("export type AgentArtifactPayload =");
    expect(source).toContain("payload: AgentArtifactPayload;");
    expect(source).not.toContain("payload: Record<string, unknown>;");
  });
});
