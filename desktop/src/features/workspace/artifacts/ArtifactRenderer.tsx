import type { AgentArtifact } from "../../../types/agentArtifact";
import { ChartArtifactView } from "./ChartArtifactView";
import { EmptyArtifactsState } from "./EmptyArtifactsState";
import { MarkdownArtifactView } from "./MarkdownArtifactView";
import { SqlArtifactView } from "./SqlArtifactView";
import { TableArtifactView } from "./TableArtifactView";

interface ArtifactRendererProps {
  artifacts: AgentArtifact[];
  onOpenSqlConsole: (initialSql?: string) => void;
  onToast: (message: string) => void;
}

export function ArtifactRenderer({ artifacts, onOpenSqlConsole, onToast }: ArtifactRendererProps) {
  if (artifacts.length === 0) {
    return <EmptyArtifactsState />;
  }

  return (
    <>
      {artifacts.map((artifact) => {
        if (artifact.type === "chart") {
          return <ChartArtifactView key={artifact.id} artifact={artifact} onToast={onToast} />;
        }
        if (artifact.type === "sql") {
          return <SqlArtifactView key={artifact.id} artifact={artifact} onOpenSqlConsole={onOpenSqlConsole} onToast={onToast} />;
        }
        if (artifact.type === "table") {
          return <TableArtifactView key={artifact.id} artifact={artifact} onToast={onToast} />;
        }
        return <MarkdownArtifactView key={artifact.id} artifact={artifact} onToast={onToast} />;
      })}
    </>
  );
}
