import type { AgentArtifact } from "../../../types/agentArtifact";
import { ChartArtifactView } from "./ChartArtifactView";
import { MarkdownArtifactView } from "./MarkdownArtifactView";
import { SqlArtifactView } from "./SqlArtifactView";
import { TableArtifactView } from "./TableArtifactView";

interface ArtifactRendererProps {
  artifacts: AgentArtifact[];
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
}

export function ArtifactRenderer({ artifacts, onOpenSqlConsole, onSetSqlQuery }: ArtifactRendererProps) {
  return (
    <>
      {artifacts.map((artifact) => {
        if (artifact.type === "chart") return <ChartArtifactView key={artifact.id} artifact={artifact} />;
        if (artifact.type === "sql") {
          return <SqlArtifactView key={artifact.id} artifact={artifact} onOpenSqlConsole={onOpenSqlConsole} onSetSqlQuery={onSetSqlQuery} />;
        }
        if (artifact.type === "table") return <TableArtifactView key={artifact.id} artifact={artifact} />;
        return <MarkdownArtifactView key={artifact.id} artifact={artifact} />;
      })}
    </>
  );
}
