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
  sql?: unknown;
  safeSql?: unknown;
  sourceRefs?: unknown;
  sourceSqlArtifactId?: unknown;
  sourceResultArtifactId?: unknown;
  safetyArtifactId?: unknown;
  queryFingerprint?: unknown;
  datasourceGeneration?: unknown;
  columns?: unknown;
  rowCount?: unknown;
  returnedRows?: unknown;
  latencyMs?: unknown;
  executedAt?: unknown;
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
  validationStatus?: unknown;
  executionStatus?: unknown;
  chartType?: unknown;
  chartable?: unknown;
  aggregation?: unknown;
  reason?: unknown;
  unit?: unknown;
  x?: unknown;
  y?: unknown;
  xLabel?: unknown;
  yLabel?: unknown;
  seriesLabel?: unknown;
  dataLabel?: unknown;
  sampleSize?: unknown;
  dimensions?: unknown;
  metrics?: unknown;
  canExecute?: unknown;
  requiresApproval?: unknown;
  passed?: unknown;
  guardrail?: unknown;
  schemaWarnings?: unknown;
  redaction?: unknown;
  redactions?: unknown;
  guardrailResult?: unknown;
  schemaWarningsCount?: unknown;
  redactionAudit?: unknown;
  audit?: unknown;
  executionSafetyDecision?: unknown;
  redactedCount?: unknown;
  redactedFields?: unknown;
  fields?: unknown;
  sensitiveFields?: unknown;
  notable_facts?: unknown;
  detected_patterns?: unknown;
  anomalies?: unknown;
  limitations?: unknown;
  recommendations?: unknown;
  followUpQuestions?: unknown;
  detail?: unknown;
}

export type AgentPlanArtifactPayload = AgentArtifactPayloadCommon & {
  steps?: Array<Record<string, unknown>>;
  intent?: Record<string, unknown>;
};

export type AgentSqlArtifactPayload = AgentArtifactPayloadCommon & {
  sql?: string;
  safeSql?: string;
};

export type AgentSafetyArtifactPayload = AgentArtifactPayloadCommon & {
  canExecute?: boolean;
  requiresApproval?: boolean;
  passed?: boolean;
};

export type AgentResultViewArtifactPayload = AgentArtifactPayloadCommon & {
  sourceSqlArtifactId: string;
  queryFingerprint: string;
  datasourceGeneration: number;
  columns: Array<string | { name: string; type?: string }>;
  rowCount: number;
  returnedRows: number;
  latencyMs: number;
  executedAt: string;
  truncated: boolean;
};

export type AgentChartArtifactPayload = AgentArtifactPayloadCommon;

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
  payload?: AgentArtifactPayload;
}
