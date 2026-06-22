import type { AgentArtifact, TableArtifact, ResultViewArtifact } from "../../../types/agentArtifact";
import { ChartArtifactView } from "./ChartArtifactView";
import { EmptyArtifactsState } from "./EmptyArtifactsState";
import { MarkdownArtifactView } from "./MarkdownArtifactView";
import { SqlArtifactView } from "./SqlArtifactView";
import { TableArtifactView } from "./TableArtifactView";

interface ArtifactRendererProps {
  artifacts: AgentArtifact[];
  onOpenSqlConsole: (initialSql?: string) => void;
  onOpenResultTab?: (artifact: TableArtifact | ResultViewArtifact) => void;
  onToast: (message: string) => void;
}

export function ArtifactRenderer({ artifacts, onOpenSqlConsole, onOpenResultTab, onToast }: ArtifactRendererProps) {
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
        if (artifact.type === "table" || artifact.type === "result_view") {
          return <TableArtifactView key={artifact.id} artifact={artifact} onOpenResultTab={onOpenResultTab} onToast={onToast} />;
        }
        return <MarkdownArtifactView key={artifact.id} artifact={artifact} onToast={onToast} />;
      })}
    </>
  );
}
