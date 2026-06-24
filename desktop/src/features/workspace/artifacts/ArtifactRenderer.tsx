import type { ReactElement } from "react";
import type {
  AgentArtifact,
  ChartArtifact,
  MarkdownArtifact,
  ResultViewArtifact,
  SqlArtifact,
} from "../../../types/agentArtifact";
import { ChartArtifactView } from "./ChartArtifactView";
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
  chart: (artifact, props) => <ChartArtifactView key={artifact.id} artifact={artifact} onToast={props.onToast} />,
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
      const fallbackArtifact = artifact as AgentArtifact;
      return (
        <MarkdownArtifactView
          key={fallbackArtifact.id}
          artifact={toFallbackMarkdownArtifact(fallbackArtifact)}
          onToast={props.onToast}
        />
      );
    }
  }
}

function toFallbackMarkdownArtifact(artifact: AgentArtifact): MarkdownArtifact {
  return {
    id: artifact.id,
    type: "markdown",
    title: artifact.title || "Artifact",
    content: JSON.stringify(artifact, null, 2),
    description: "暂不支持的产物类型，已按原始 JSON 展示。",
  };
}
