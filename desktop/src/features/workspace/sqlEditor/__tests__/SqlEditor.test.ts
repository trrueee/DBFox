import { CompletionContext } from "@codemirror/autocomplete";
import { EditorState } from "@codemirror/state";
import { describe, expect, it, vi } from "vitest";

import type { EngineColumn, EngineSchemaTable } from "../../../../lib/api/schema";
import { defaultSql } from "../../defaultSql";
import { buildSchemaNamespace, createQualifiedColumnSource } from "../sqlCompletion";

function table(id: string, schema: string, name: string): EngineSchemaTable {
  return {
    id,
    table_schema: schema,
    table_name: name,
    table_comment: "",
    columns_count: 0,
    row_count_estimate: null,
    ai_description: "",
    semantic_tags: "",
    business_terms: "",
    subject_area: "",
  };
}

function column(name: string, dataType: string): EngineColumn {
  return {
    id: `column-${name}`,
    column_name: name,
    data_type: dataType,
    column_type: dataType,
    is_nullable: true,
    column_default: "",
    column_comment: "",
    is_primary_key: false,
    is_foreign_key: false,
    ai_description: "",
    semantic_tags: "",
    business_terms: "",
  };
}

describe("SQL editor completion catalog", () => {
  it("projects database schemas and tables into the CodeMirror namespace", () => {
    const result = buildSchemaNamespace([
      table("table-orders", "creatorhub", "orders"),
      table("table-users", "creatorhub", "users"),
    ]);

    expect(result.defaultSchema).toBe("creatorhub");
    expect(result.schema).toEqual({
      creatorhub: {
        self: expect.objectContaining({
          label: "creatorhub",
          type: "namespace",
          detail: "Schema",
          boost: 10,
          section: expect.objectContaining({ name: "Schema" }),
        }),
        children: {
          orders: {
            self: expect.objectContaining({
              label: "orders",
              type: "class",
              detail: "数据表",
              boost: 20,
              section: expect.objectContaining({ name: "数据表" }),
            }),
            children: [],
          },
          users: {
            self: expect.objectContaining({ label: "users", type: "class" }),
            children: [],
          },
        },
      },
    });
  });

  it("starts new consoles with an empty draft instead of instructional SQL", () => {
    expect(defaultSql).toBe("");
  });

  it("loads columns only when a unique physical table qualifier is completed", async () => {
    const loadColumns = vi.fn().mockResolvedValue([
      column("id", "bigint"),
      column("created_at", "datetime"),
    ]);
    const source = createQualifiedColumnSource(
      [table("table-orders", "creatorhub", "orders")],
      loadColumns,
    );
    const state = EditorState.create({ doc: "SELECT orders. FROM orders" });
    const result = await source(new CompletionContext(state, "SELECT orders.".length, true));

    expect(loadColumns).toHaveBeenCalledWith("table-orders");
    expect(result?.from).toBe("SELECT orders.".length);
    expect(result?.options).toEqual([
      expect.objectContaining({
        label: "id",
        type: "property",
        detail: "bigint",
        boost: 30,
        section: expect.objectContaining({ name: "字段" }),
      }),
      expect.objectContaining({
        label: "created_at",
        type: "property",
        detail: "datetime",
        boost: 30,
      }),
    ]);
  });

  it("does not guess columns when the same table name exists in multiple schemas", async () => {
    const loadColumns = vi.fn();
    const source = createQualifiedColumnSource(
      [
        table("table-a", "public", "orders"),
        table("table-b", "archive", "orders"),
      ],
      loadColumns,
    );
    const state = EditorState.create({ doc: "SELECT orders." });
    const result = await source(new CompletionContext(state, state.doc.length, true));

    expect(result).toBeNull();
    expect(loadColumns).not.toHaveBeenCalled();
  });

  it("uses an explicit schema to disambiguate duplicate table names", async () => {
    const loadColumns = vi.fn().mockResolvedValue([column("id", "bigint")]);
    const source = createQualifiedColumnSource(
      [
        table("table-a", "public", "orders"),
        table("table-b", "archive", "orders"),
      ],
      loadColumns,
    );
    const state = EditorState.create({ doc: "SELECT archive.orders." });
    const result = await source(new CompletionContext(state, state.doc.length, true));

    expect(loadColumns).toHaveBeenCalledWith("table-b");
    expect(result?.options).toEqual([expect.objectContaining({ label: "id" })]);
  });

  it("keeps editor completion optional when column metadata cannot be loaded", async () => {
    const loadColumns = vi.fn().mockRejectedValue(new Error("offline"));
    const source = createQualifiedColumnSource(
      [table("table-orders", "creatorhub", "orders")],
      loadColumns,
    );
    const state = EditorState.create({ doc: "SELECT orders." });

    await expect(source(new CompletionContext(state, state.doc.length, true))).resolves.toBeNull();
  });
});
