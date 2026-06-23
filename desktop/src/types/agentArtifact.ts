export type AgentArtifactType = "chart" | "sql" | "table" | "result_view" | "markdown";

export type AgentArtifactBase = {
  id: string;
  type: AgentArtifactType;
  title: string;
  description?: string;
  depends_on?: string[];
  payload?: Record<string, unknown>;
  references?: DataReference[];
};

export type ChartArtifactType = "line" | "bar" | "pie" | "scatter" | "area";

export type ChartArtifact = AgentArtifactBase & {
  type: "chart";
  chartType: ChartArtifactType;
  unit?: string;
  xLabel?: string;
  yLabel?: string;
  seriesLabel?: string;
  dataLabel?: boolean;
  sampleSize?: number;
  dimensions?: Array<{ name?: string; column?: string; role?: string; kind?: string }>;
  metrics?: Array<{ name?: string; source_column?: string; expression?: string; aggregation?: string; role?: string }>;
  series: Array<{ label: string; value: number; x?: string | number; y?: number }>;
  sourceRefs?: Array<{ label: string; formula: string; field: string }>;
};

export type SqlArtifact = AgentArtifactBase & {
  type: "sql";
  sql: string;
  purpose?: string;
  usedTables?: string[];
  validationStatus?: string;
  executionStatus?: string;
  rowCount?: number;
  latencyMs?: number;
};

export type TableArtifact = AgentArtifactBase & {
  type: "table";
  columns: string[];
  rows: string[][];
  rowCount?: number;
  returnedRows?: number;
  latencyMs?: number;
  sql?: string;
  truncated?: boolean;
  warnings?: string[];
  notices?: string[];
};

export type ResultViewArtifact = AgentArtifactBase & {
  type: "result_view";
  storageMode: "payload" | "sql_backed";
  datasourceId: string;
  sourceSqlSemanticId: string;
  sourceSql: string;
  safeSql: string;
  columns: string[];
  previewRows: string[][];
  previewRowCount: number;
  rows?: string[][]; // For legacy compatibility
  rowCount?: number;
  returnedRows?: number;
  latencyMs?: number;
  truncated?: boolean;
  warnings?: string[];
  notices?: string[];
};

export type MarkdownArtifact = AgentArtifactBase & {
  type: "markdown";
  content: string;
};

export type AgentArtifact = ChartArtifact | SqlArtifact | TableArtifact | ResultViewArtifact | MarkdownArtifact;

export type DataReference =
  | { type: "table"; datasourceId?: string; schema?: string; table: string; label: string }
  | { type: "column"; datasourceId?: string; schema?: string; table?: string; column: string; label: string }
  | { type: "sql"; artifactId: string; label: string; sql?: string }
  | { type: "result"; artifactId: string; rowCount?: number; label: string }
  | { type: "chart"; artifactId: string; label: string };
