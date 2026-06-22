export type AgentArtifactType = "chart" | "sql" | "table" | "markdown";

export type AgentArtifactBase = {
  id: string;
  type: AgentArtifactType;
  title: string;
  description?: string;
  depends_on?: string[];
  payload?: Record<string, unknown>;
  references?: DataReference[];
};

export type ChartArtifact = AgentArtifactBase & {
  type: "chart";
  chartType: "line" | "bar";
  unit?: string;
  series: Array<{ label: string; value: number }>;
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

export type MarkdownArtifact = AgentArtifactBase & {
  type: "markdown";
  content: string;
};

export type AgentArtifact = ChartArtifact | SqlArtifact | TableArtifact | MarkdownArtifact;

export type DataReference =
  | { type: "table"; datasourceId?: string; schema?: string; table: string; label: string }
  | { type: "column"; datasourceId?: string; schema?: string; table?: string; column: string; label: string }
  | { type: "sql"; artifactId: string; label: string; sql?: string }
  | { type: "result"; artifactId: string; rowCount?: number; label: string }
  | { type: "chart"; artifactId: string; label: string };
