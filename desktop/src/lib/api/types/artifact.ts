export interface AgentArtifactPayloadCommon {
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

export interface AgentSqlArtifactPayload {
  sql: string;
  safeSql: string;
  dialect: string;
  queryFingerprint: string;
  parameters?: Record<string, unknown>;
}

export type AgentSafetyArtifactPayload = AgentArtifactPayloadCommon & {
  canExecute?: boolean;
  requiresApproval?: boolean;
  passed?: boolean;
};

export interface AgentResultViewArtifactPayload {
  sourceSqlArtifactId: string;
  queryFingerprint: string;
  datasourceGeneration: number | null;
  columns: Array<string | { name: string; type?: string }>;
  rowCount: number;
  returnedRows: number;
  latencyMs: number | null;
  executedAt: string;
  truncated: boolean;
}

export interface AgentChartArtifactPayload {
  sourceResultArtifactId: string;
  chartType: string;
  x?: string | null;
  y: string[];
  aggregation?: string | null;
  title?: string | null;
}

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
