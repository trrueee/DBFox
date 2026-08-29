import { describe, expect, it } from "vitest";
import { DATAFRAME_REPRESENTATION_TYPE } from "../../../../lib/api/representation";
import {
  createArtifactViewRegistry,
  matchingArtifactViews,
  productArtifactViews,
} from "../artifactViewRegistry";
import type { ArtifactEnvelope, ArtifactViewContribution } from "../types";

const result: ArtifactEnvelope = {
  id: "result-1",
  type: "dbfox.data.result_view",
  schema_version: 2,
  title: "Result",
  payload: { sourceSqlArtifactId: "sql-1" },
};

const dataArtifactViews: ArtifactViewContribution<unknown>[] = [
  {
    id: "dbfox.data.source-sql",
    title: "来源 SQL",
    surfaces: ["workspace"],
    artifactTypes: [{ type: "dbfox.data.result_view", schemaVersions: [2] }],
    parsePayload: (value) => value,
    render: () => null,
  },
  {
    id: "dbfox.data.sql",
    title: "SQL",
    surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: "dbfox.data.sql", schemaVersions: [1] }],
    parsePayload: (value) => value,
    render: () => null,
  },
];

const allViews = () => [...productArtifactViews(), ...dataArtifactViews];

describe("Artifact View registry", () => {
  it("allows multiple named Views for the same Artifact", () => {
    const views = matchingArtifactViews(
      result,
      [{
        representation_type: DATAFRAME_REPRESENTATION_TYPE,
        version: 1,
        operations: [{ name: "page", result_kind: "json" }],
      }],
      "workspace",
      allViews(),
    );

    expect(views.map((view) => view.id)).toEqual([
      "core.dataframe.table",
      "dbfox.data.source-sql",
    ]);
  });

  it("keeps representation-backed Views unavailable until discovery proves support", () => {
    const views = matchingArtifactViews(result, [], "inline", productArtifactViews());
    expect(views.map((view) => view.id)).not.toContain("core.dataframe.table");
  });

  it("matches Artifact type and schema version without teaching Dock about the domain", () => {
    const sql: ArtifactEnvelope = {
      id: "sql-1",
      type: "dbfox.data.sql",
      schema_version: 1,
      title: "SQL",
      payload: { sql: "SELECT 1" },
    };
    expect(matchingArtifactViews(sql, [], "workspace", allViews())
      .map((view) => view.id)).toEqual(["dbfox.data.sql"]);
  });

  it("keeps Data Artifact type knowledge out of the Host registry", () => {
    const sql: ArtifactEnvelope = {
      id: "sql-1",
      type: "dbfox.data.sql",
      schema_version: 1,
      title: "SQL",
      payload: { sql: "SELECT 1" },
    };
    expect(matchingArtifactViews(sql, [], "workspace", productArtifactViews())).toEqual([]);
  });

  it("rejects duplicate global View ids", () => {
    const duplicate: ArtifactViewContribution<unknown> = {
      id: "acme.view",
      title: "ACME",
      surfaces: ["inline"],
      artifactTypes: [{ type: "acme.artifact" }],
      parsePayload: (value) => value,
      render: () => null,
    };
    expect(() => createArtifactViewRegistry([duplicate, duplicate])).toThrow(
      /Duplicate Artifact View id/,
    );
  });

  it("does not expose workspace-only related Views inline", () => {
    const views = matchingArtifactViews(
      result,
      [{
        representation_type: DATAFRAME_REPRESENTATION_TYPE,
        version: 1,
        operations: [{ name: "page", result_kind: "json" }],
      }],
      "inline",
      allViews(),
    );
    expect(views.map((view) => view.id)).toEqual(["core.dataframe.table"]);
  });
});
