export type AgentArtifactType = "chart" | "sql" | "result_view" | "markdown";

export type AgentArtifactBase = {
  id: string;
  type: AgentArtifactType;
  title: string;
  description?: string;
  depends_on?: string[];
  references?: DataReference[];
};

export type ChartArtifactType = "line" | "bar" | "pie" | "scatter" | "area";

export type ChartPoint = { label: string; value: number; x?: string | number; y?: number };

export type ChartArtifact = AgentArtifactBase & {
  type: "chart";
  chartType: ChartArtifactType;
  sourceResultArtifactId: string;
  x: string;
  y: string[];
  aggregation: "sum" | "none" | null;
};

export type RenderedChartArtifact = ChartArtifact & { series: ChartPoint[] };

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

export type ResultArtifactColumn = string | { name: string; type?: string };

export type ResultViewArtifact = AgentArtifactBase & {
  type: "result_view";
  sourceSqlArtifactId: string;
  columns: ResultArtifactColumn[];
  queryFingerprint: string;
  datasourceGeneration?: number;
  rowCount?: number;
  returnedRows?: number;
  latencyMs?: number;
  truncated?: boolean;
};

export type MarkdownArtifact = AgentArtifactBase & {
  type: "markdown";
  content: string;
};

export type AgentArtifact = ChartArtifact | SqlArtifact | ResultViewArtifact | MarkdownArtifact;

export type DataReference =
  | { type: "table"; datasourceId?: string; schema?: string; table: string; label: string }
  | { type: "column"; datasourceId?: string; schema?: string; table?: string; column: string; label: string }
  | { type: "sql"; artifactId: string; label: string; sql?: string }
  | { type: "result"; artifactId: string; rowCount?: number; label: string }
  | { type: "chart"; artifactId: string; label: string };
