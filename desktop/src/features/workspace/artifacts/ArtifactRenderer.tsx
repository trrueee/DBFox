import type { AgentArtifact, AgentArtifactType } from "../../../types/agentArtifact";
import { ChartArtifactView } from "./ChartArtifactView";
import { EmptyArtifactsState } from "./EmptyArtifactsState";
import { MarkdownArtifactView } from "./MarkdownArtifactView";
import { MetricArtifactView } from "./MetricArtifactView";
import { SqlArtifactView } from "./SqlArtifactView";
import { TableArtifactView } from "./TableArtifactView";
import { TraceArtifactView } from "./TraceArtifactView";

type DisplayPlanComponent = "metric" | "chart" | "table" | "markdown" | "recommendation" | "sql" | "trace";

export interface ArtifactDisplayPlanItem {
  component: DisplayPlanComponent;
  reason?: string;
  priority?: number;
}

interface ArtifactRendererProps {
  artifacts: AgentArtifact[];
  displayPlan?: ArtifactDisplayPlanItem[];
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
  onToast: (message: string) => void;
}

const COMPONENT_TYPES: Record<DisplayPlanComponent, AgentArtifactType[]> = {
  metric: ["metric"],
  chart: ["chart"],
  table: ["table"],
  markdown: ["markdown"],
  recommendation: ["markdown"],
  sql: ["sql"],
  trace: ["trace"],
};

const FALLBACK_TYPE_ORDER: Record<AgentArtifactType, number> = {
  metric: 10,
  chart: 20,
  table: 30,
  markdown: 40,
  sql: 80,
  trace: 90,
};

export function ArtifactRenderer({ artifacts, displayPlan, onOpenSqlConsole, onSetSqlQuery, onToast }: ArtifactRendererProps) {
  if (artifacts.length === 0) {
    return <EmptyArtifactsState />;
  }

  const orderedArtifacts = orderArtifactsByDisplayPlan(artifacts, displayPlan);

  return (
    <>
      {orderedArtifacts.map((artifact) => {
        if (artifact.type === "metric") {
          return <MetricArtifactView key={artifact.id} artifact={artifact} />;
        }
        if (artifact.type === "chart") {
          return <ChartArtifactView key={artifact.id} artifact={artifact} onToast={onToast} />;
        }
        if (artifact.type === "sql") {
          return <SqlArtifactView key={artifact.id} artifact={artifact} onOpenSqlConsole={onOpenSqlConsole} onSetSqlQuery={onSetSqlQuery} onToast={onToast} />;
        }
        if (artifact.type === "table") {
          return <TableArtifactView key={artifact.id} artifact={artifact} onToast={onToast} />;
        }
        if (artifact.type === "trace") {
          return <TraceArtifactView key={artifact.id} artifact={artifact} />;
        }
        return <MarkdownArtifactView key={artifact.id} artifact={artifact} onToast={onToast} />;
      })}
    </>
  );
}

function orderArtifactsByDisplayPlan(artifacts: AgentArtifact[], displayPlan?: ArtifactDisplayPlanItem[]): AgentArtifact[] {
  if (!displayPlan?.length) {
    return [...artifacts].sort((a, b) => (FALLBACK_TYPE_ORDER[a.type] ?? 100) - (FALLBACK_TYPE_ORDER[b.type] ?? 100));
  }

  const remaining = [...artifacts];
  const ordered: AgentArtifact[] = [];

  const plan = [...displayPlan].sort((a, b) => (a.priority ?? 100) - (b.priority ?? 100));
  for (const item of plan) {
    const targetTypes = COMPONENT_TYPES[item.component] ?? [];
    if (targetTypes.length === 0) continue;

    for (let index = 0; index < remaining.length;) {
      const artifact = remaining[index];
      if (targetTypes.includes(artifact.type)) {
        ordered.push(artifact);
        remaining.splice(index, 1);
        continue;
      }
      index += 1;
    }
  }

  remaining.sort((a, b) => (FALLBACK_TYPE_ORDER[a.type] ?? 100) - (FALLBACK_TYPE_ORDER[b.type] ?? 100));
  return [...ordered, ...remaining];
}
