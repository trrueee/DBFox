import { describe, expectTypeOf, it } from "vitest";

import type { AgentArtifactPayload, AgentResultViewArtifactPayload } from "../types/artifact";
import type { DataSourceResponse, SchemaSyncResponse } from "../generated/types.gen";

describe("API type contracts", () => {
  it("keeps schema synchronization counters closed and numeric", () => {
    expectTypeOf<SchemaSyncResponse["tablesDropped"]>().toEqualTypeOf<number>();
    expectTypeOf<SchemaSyncResponse["columnsCreated"]>().toEqualTypeOf<number>();
    expectTypeOf<SchemaSyncResponse["columnsUpdated"]>().toEqualTypeOf<number>();
    expectTypeOf<SchemaSyncResponse["columnsRemoved"]>().toEqualTypeOf<number>();
  });

  it("models nullable datasource connection fields", () => {
    expectTypeOf<DataSourceResponse["host"]>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<DataSourceResponse["username"]>().toEqualTypeOf<string | null | undefined>();
  });

  it("keeps result artifacts as one explicit payload variant", () => {
    expectTypeOf<AgentResultViewArtifactPayload>().toMatchTypeOf<AgentArtifactPayload>();
    expectTypeOf<AgentResultViewArtifactPayload["sourceSqlArtifactId"]>().toEqualTypeOf<string>();
    expectTypeOf<AgentResultViewArtifactPayload["columns"]>().toEqualTypeOf<
      Array<string | { name: string; type?: string }>
    >();
  });
});
