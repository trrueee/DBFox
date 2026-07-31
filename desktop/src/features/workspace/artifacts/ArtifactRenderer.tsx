import type { ReactElement } from "react";
import { FileQuestion } from "lucide-react";
import type {
  AgentArtifact,
  ChartArtifact,
  MarkdownArtifact,
  ResultViewArtifact,
  SqlArtifact,
} from "../../../types/agentArtifact";
import { DeferredChartArtifactView } from "./DeferredChartArtifactView";
import { EmptyArtifactsState } from "./EmptyArtifactsState";
import { MarkdownArtifactView } from "./MarkdownArtifactView";
import { SqlArtifactView } from "./SqlArtifactView";
import { TableArtifactView } from "./TableArtifactView";

interface ArtifactRendererProps {
  artifacts: AgentArtifact[];
  onOpenSqlConsole: (initialSql?: string) => void;
  onOpenResultTab?: (artifact: ResultViewArtifact) => void;
  onToast: (message: string) => void;
}

type ArtifactRendererMap = {
  chart: (artifact: ChartArtifact, props: ArtifactRendererProps) => ReactElement;
  sql: (artifact: SqlArtifact, props: ArtifactRendererProps) => ReactElement;
  result_view: (artifact: ResultViewArtifact, props: ArtifactRendererProps) => ReactElement;
  markdown: (artifact: MarkdownArtifact, props: ArtifactRendererProps) => ReactElement;
};

const ARTIFACT_RENDERERS: ArtifactRendererMap = {
  chart: (artifact, props) => <DeferredChartArtifactView key={artifact.id} artifact={artifact} onToast={props.onToast} />,
  sql: (artifact, props) => (
    <SqlArtifactView
      key={artifact.id}
      artifact={artifact}
      onOpenSqlConsole={props.onOpenSqlConsole}
      onToast={props.onToast}
    />
  ),
  result_view: (artifact, props) => (
    <TableArtifactView
      key={artifact.id}
      artifact={artifact}
      onOpenResultTab={props.onOpenResultTab}
      onToast={props.onToast}
    />
  ),
  markdown: (artifact, props) => <MarkdownArtifactView key={artifact.id} artifact={artifact} onToast={props.onToast} />,
};

export function ArtifactRenderer({ artifacts, onOpenSqlConsole, onOpenResultTab, onToast }: ArtifactRendererProps) {
  if (artifacts.length === 0) {
    return <EmptyArtifactsState />;
  }

  const props = { artifacts, onOpenSqlConsole, onOpenResultTab, onToast };

  return (
    <>
      {artifacts.map((artifact) => renderArtifact(artifact, props))}
    </>
  );
}

function renderArtifact(artifact: AgentArtifact, props: ArtifactRendererProps) {
  switch (artifact.type) {
    case "chart":
      return ARTIFACT_RENDERERS.chart(artifact, props);
    case "sql":
      return ARTIFACT_RENDERERS.sql(artifact, props);
    case "result_view":
      return ARTIFACT_RENDERERS.result_view(artifact, props);
    case "markdown":
      return ARTIFACT_RENDERERS.markdown(artifact, props);
    default: {
      const unsupportedArtifact = artifact as AgentArtifact;
      return (
        <section className="artifact-card artifact-unsupported" key={unsupportedArtifact.id} role="status">
          <span className="artifact-unsupported__icon" aria-hidden="true">
            <FileQuestion size={18} />
          </span>
          <div className="artifact-unsupported__copy">
            <strong>{unsupportedArtifact.title || "暂不支持预览的工件"}</strong>
            <span>此工件的引用已安全保留，当前版本暂不支持直接预览。</span>
          </div>
        </section>
      );
    }
  }
}
