import type { AgentArtifact } from "../../../types/agentArtifact";
import { ChartArtifactView } from "./ChartArtifactView";
import { EmptyArtifactsState } from "./EmptyArtifactsState";
import { MarkdownArtifactView } from "./MarkdownArtifactView";
import { MetricArtifactView } from "./MetricArtifactView";
import { SqlArtifactView } from "./SqlArtifactView";
import { TableArtifactView } from "./TableArtifactView";
import { TraceArtifactView } from "./TraceArtifactView";

interface ArtifactRendererProps {
  artifacts: AgentArtifact[];
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
  onToast: (message: string) => void;
}

export function ArtifactRenderer({ artifacts, onOpenSqlConsole, onSetSqlQuery, onToast }: ArtifactRendererProps) {
  if (artifacts.length === 0) {
    return <EmptyArtifactsState />;
  }

  return (
    <>
      {artifacts.map((artifact) => {
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
