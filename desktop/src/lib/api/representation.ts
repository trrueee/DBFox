import type { ArtifactRepresentationResult } from "./generated/types.gen";

export const DATAFRAME_REPRESENTATION_TYPE = "dbfox.dataframe.v1";

export type DataFrameScalar = string | number | boolean | null;
export type DataFrameFilterOperator =
  | "equals"
  | "not_equals"
  | "contains"
  | "starts_with"
  | "ends_with"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "is_null"
  | "is_not_null"
  | "in"
  | "not_in";

export interface DataFrameFilter {
  field: string;
  operator: DataFrameFilterOperator;
  value?: DataFrameScalar | DataFrameScalar[];
}

export interface DataFrameSort {
  field: string;
  direction: "asc" | "desc";
}

export interface DataFramePageRequest {
  page: number;
  page_size: number;
  sort?: DataFrameSort[];
  filters?: DataFrameFilter[];
  search?: string;
  count_mode?: "none" | "exact" | "estimate";
}

export interface DataFrameExportRequest {
  sort?: DataFrameSort[];
  filters?: DataFrameFilter[];
  search?: string;
}

export interface DataFrameField {
  key: string;
  name: string;
  type: string;
  nullable: boolean;
  semantic_type?: string | null;
  unit?: string | null;
  values: DataFrameScalar[];
}

export interface DataFramePage {
  fields: DataFrameField[];
  page: number;
  page_size: number;
  row_count?: number | null;
  has_next_page: boolean;
  latency_ms: number;
  source_truncated: boolean;
}

export interface DataFrameRead {
  page: DataFramePage;
  rows: Record<string, DataFrameScalar>[];
  consistency: "durable_snapshot" | "live_reexecution";
  originalObservedAt?: string | null;
  readAt: string;
  readId: string;
  sourceVersion: string;
  sourceFingerprint: string;
  warnings: string[];
  notices: string[];
}

export function parseDataFrameRead(result: ArtifactRepresentationResult): DataFrameRead {
  if (
    result.representation_type !== DATAFRAME_REPRESENTATION_TYPE
    || result.representation_version !== 1
    || result.operation !== "page"
  ) {
    throw new TypeError("The Artifact did not return dbfox.dataframe.v1 page data.");
  }
  const page = parseDataFramePage(result.payload);
  return {
    page,
    rows: Array.from({ length: page.fields[0]?.values.length ?? 0 }, (_, index) => (
      Object.fromEntries(page.fields.map((field) => [field.name, field.values[index] ?? null]))
    )),
    consistency: result.consistency,
    originalObservedAt: result.original_observed_at,
    readAt: result.read_at,
    readId: result.read_id,
    sourceVersion: result.source_version,
    sourceFingerprint: result.source_fingerprint,
    warnings: result.warnings ?? [],
    notices: result.notices ?? [],
  };
}

function parseDataFramePage(value: unknown): DataFramePage {
  if (!isRecord(value) || !Array.isArray(value.fields)) {
    throw new TypeError("The DataFrame page payload is invalid.");
  }
  const fields = value.fields.map(parseField);
  const vectorLength = fields[0]?.values.length ?? 0;
  if (fields.some((field) => field.values.length !== vectorLength)) {
    throw new TypeError("The DataFrame field vectors have inconsistent lengths.");
  }
  return {
    fields,
    page: requiredInteger(value.page, "page"),
    page_size: requiredInteger(value.page_size, "page_size"),
    row_count: value.row_count == null ? null : requiredInteger(value.row_count, "row_count"),
    has_next_page: requiredBoolean(value.has_next_page, "has_next_page"),
    latency_ms: requiredInteger(value.latency_ms, "latency_ms"),
    source_truncated: requiredBoolean(value.source_truncated, "source_truncated"),
  };
}

function parseField(value: unknown): DataFrameField {
  if (!isRecord(value) || !Array.isArray(value.values)) {
    throw new TypeError("A DataFrame field is invalid.");
  }
  const values = value.values.map((item) => {
    if (item == null || ["string", "number", "boolean"].includes(typeof item)) return item as DataFrameScalar;
    throw new TypeError("A DataFrame field contains an invalid scalar.");
  });
  return {
    key: requiredString(value.key, "field.key"),
    name: requiredString(value.name, "field.name"),
    type: requiredString(value.type, "field.type"),
    nullable: requiredBoolean(value.nullable, "field.nullable"),
    semantic_type: optionalString(value.semantic_type),
    unit: optionalString(value.unit),
    values,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value) throw new TypeError(`Invalid ${field}.`);
  return value;
}

function optionalString(value: unknown): string | null | undefined {
  if (value == null) return value;
  if (typeof value !== "string") throw new TypeError("Invalid optional DataFrame string.");
  return value;
}

function requiredInteger(value: unknown, field: string): number {
  if (!Number.isInteger(value) || (value as number) < 0) throw new TypeError(`Invalid ${field}.`);
  return value as number;
}

function requiredBoolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") throw new TypeError(`Invalid ${field}.`);
  return value;
}
