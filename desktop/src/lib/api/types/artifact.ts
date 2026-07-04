import type { AgentIntentPlan, AgentPlanStep } from "./agent";

export type AgentArtifactType =
  | "agent_plan"
  | "query_plan"
  | "sql"
  | "sql_suggestion"
  | "safety"
  | "result_view"
  | "chart"
  | "error"
  | "insight"
  | "recommendation";

export interface AgentArtifactPayloadCommon {
  [key: string]: unknown;
  sql?: unknown;
  proposed_sql?: unknown;
  safeSql?: unknown;
  safe_sql?: unknown;
  sourceSql?: unknown;
  source_sql?: unknown;
  source_refs?: unknown;
  storageMode?: unknown;
  storage_mode?: unknown;
  datasourceId?: unknown;
  datasource_id?: unknown;
  sourceSqlArtifactKey?: unknown;
  sourceSqlSemanticKey?: unknown;
  sourceSqlArtifactId?: unknown;
  sourceSqlSemanticId?: unknown;
  source_sql_artifact_id?: unknown;
  source_sql_semantic_id?: unknown;
  safetyArtifactKey?: unknown;
  safetySemanticKey?: unknown;
  safetyArtifactId?: unknown;
  safetySemanticId?: unknown;
  safety_artifact_id?: unknown;
  safety_semantic_id?: unknown;
  rows?: unknown;
  data?: unknown;
  previewRows?: unknown;
  preview_rows?: unknown;
  columns?: unknown;
  rowCount?: unknown;
  row_count?: unknown;
  returnedRows?: unknown;
  returned_rows?: unknown;
  previewRowCount?: unknown;
  preview_row_count?: unknown;
  latencyMs?: unknown;
  latency_ms?: unknown;
  truncated?: unknown;
  warnings?: unknown;
  notices?: unknown;
  content?: unknown;
  markdown?: unknown;
  message?: unknown;
  error?: unknown;
  description?: unknown;
  purpose?: unknown;
  usedTables?: unknown;
  used_tables?: unknown;
  validationStatus?: unknown;
  validation_status?: unknown;
  executionStatus?: unknown;
  execution_status?: unknown;
  series?: unknown;
  type?: unknown;
  chart_type?: unknown;
  kind?: unknown;
  reason?: unknown;
  unit?: unknown;
  x?: unknown;
  y?: unknown;
  xLabel?: unknown;
  x_label?: unknown;
  yLabel?: unknown;
  y_label?: unknown;
  seriesLabel?: unknown;
  series_label?: unknown;
  dataLabel?: unknown;
  data_label?: unknown;
  sampleSize?: unknown;
  sample_size?: unknown;
  dimensions?: unknown;
  metrics?: unknown;
  can_execute?: unknown;
  canExecute?: unknown;
  requires_confirmation?: unknown;
  requiresConfirmation?: unknown;
  passed?: unknown;
  guardrail?: unknown;
  schemaWarnings?: unknown;
  schema_warnings?: unknown;
  redaction?: unknown;
  redactions?: unknown;
}

export type AgentPlanArtifactPayload = AgentArtifactPayloadCommon & {
  steps?: AgentPlanStep[];
  intent?: AgentIntentPlan;
};

export type AgentSqlArtifactPayload = AgentArtifactPayloadCommon & {
  sql?: string;
  proposed_sql?: string;
  safeSql?: string;
  safe_sql?: string;
};

export type AgentSafetyArtifactPayload = AgentArtifactPayloadCommon & {
  can_execute?: boolean;
  canExecute?: boolean;
  requires_confirmation?: boolean;
  requiresConfirmation?: boolean;
  passed?: boolean;
};

export type AgentResultViewArtifactPayload = AgentArtifactPayloadCommon & {
  columns?: string[];
  rows?: Array<Record<string, unknown> | unknown[]>;
  previewRows?: Array<Record<string, unknown> | unknown[]>;
  preview_rows?: Array<Record<string, unknown> | unknown[]>;
  rowCount?: number;
  row_count?: number;
};

export type AgentChartArtifactPayload = AgentArtifactPayloadCommon & {
  series?: Array<Record<string, unknown>>;
};

export type AgentTextArtifactPayload = AgentArtifactPayloadCommon & {
  content?: string;
  markdown?: string;
  message?: string;
  error?: string;
  description?: string;
  reason?: string;
};

export type AgentArtifactPayload =
  | AgentPlanArtifactPayload
  | AgentSqlArtifactPayload
  | AgentSafetyArtifactPayload
  | AgentResultViewArtifactPayload
  | AgentChartArtifactPayload
  | AgentTextArtifactPayload;

export interface AgentArtifact {
  id: string;
  semantic_id?: string | null;
  type: AgentArtifactType;
  title: string;
  payload: AgentArtifactPayload;
  presentation: {
    mode: "inline" | "dock" | "both" | "hidden";
    priority: number;
    collapsed?: boolean;
  };
  refs?: Record<string, unknown>;
  produced_by_step?: string | null;
  depends_on?: string[];
}

// Artifact categorization — matches backend EVIDENCE_ARTIFACT_TYPES / PROCESS_ARTIFACT_TYPES
export const EVIDENCE_ARTIFACT_TYPES = new Set(["table", "chart", "sql"]);
export const PROCESS_ARTIFACT_TYPES = new Set(["query_plan", "sql_suggestion", "safety", "agent_plan", "error"]);

export interface AgentArtifactRecord {
  id: string;
  run_id?: string;
  type?: string;
  title?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}
