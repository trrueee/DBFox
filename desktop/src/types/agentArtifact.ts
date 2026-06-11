export type AgentArtifactType = "chart" | "sql" | "table" | "markdown" | "metric" | "trace";

export type AgentArtifactBase = {
  id: string;
  type: AgentArtifactType;
  title: string;
  description?: string;
};

export type ChartArtifact = AgentArtifactBase & {
  type: "chart";
  chartType: "line" | "bar";
  unit?: string;
  series: Array<{ label: string; value: number }>;
};

export type SqlArtifact = AgentArtifactBase & {
  type: "sql";
  sql: string;
};

export type TableArtifact = AgentArtifactBase & {
  type: "table";
  columns: string[];
  rows: string[][];
};

export type MarkdownArtifact = AgentArtifactBase & {
  type: "markdown";
  content: string;
};

export type MetricArtifact = AgentArtifactBase & {
  type: "metric";
  cards: Array<{
    label: string;
    value: string;
    helper?: string;
    tone?: "neutral" | "good" | "warn" | "danger";
  }>;
};

export type TraceArtifact = AgentArtifactBase & {
  type: "trace";
  stages: Array<{
    label: string;
    status: "success" | "running" | "warning" | "failed" | "skipped";
    detail?: string;
  }>;
};

export type AgentArtifact = ChartArtifact | SqlArtifact | TableArtifact | MarkdownArtifact | MetricArtifact | TraceArtifact;
