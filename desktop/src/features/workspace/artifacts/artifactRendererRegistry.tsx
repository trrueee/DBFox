import type { ReactNode } from "react";
import { FileWarning } from "lucide-react";
import { ArtifactCard } from "./ArtifactCard";
import { DeferredChartArtifactView } from "./DeferredChartArtifactView";
import { MarkdownArtifactView } from "./MarkdownArtifactView";
import { SqlArtifactView } from "./SqlArtifactView";
import { TableArtifactView } from "./TableArtifactView";
import { WorkspaceCodePatchArtifactView } from "./WorkspaceCodePatchArtifactView";
import { WorkspaceFileSnapshotArtifactView } from "./WorkspaceFileSnapshotArtifactView";
import type {
  ChartArtifact,
  MarkdownArtifact,
  ResultViewArtifact,
  SqlArtifact,
  WorkspaceCodePatchArtifact,
  WorkspaceFileSnapshotArtifact,
} from "../../../types/agentArtifact";

/**
 * Artifact renderer contribution point.
 *
 * Known renderers bind to a concrete (type, schemaVersion) pair and strictly
 * parse their payload. Unknown historical types keep the envelope and render
 * the metadata fallback below; unknown new versions are never guessed.
 */

export interface ArtifactEnvelope<TPayload = Record<string, unknown>> {
  id: string;
  type: string;
  schema_version?: number;
  title: string;
  summary?: string | null;
  payload?: TPayload | null;
  payload_ref?: string | null;
  provenance?: Record<string, unknown>;
  relations?: Array<{ relation: string; artifact_id: string }>;
  status?: string;
  visibility?: string;
  version?: number;
}

export interface ArtifactRendererContext {
  onToast: (message: string) => void;
  onOpenSqlConsole?: (initialSql?: string) => void;
  onOpenResultTab?: (artifact: ResultViewArtifact) => void;
  sourceSqlArtifact?: SqlArtifact;
  compact?: boolean;
  mode?: "inline" | "workspace";
}

export interface ArtifactRendererContribution<TPayload> {
  type: string;
  supportedSchemaVersions: readonly number[];
  parsePayload(value: unknown): TPayload;
  render(
    artifact: ArtifactEnvelope<TPayload>,
    context: ArtifactRendererContext,
  ): ReactNode;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Artifact payload must be an object");
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Artifact payload requires ${field}`);
  }
  return value;
}

function parseResultViewPayload(value: unknown): ResultViewArtifact {
  const payload = asRecord(value);
  const columns = payload.columns;
  if (!Array.isArray(columns)) {
    throw new Error("result_view payload requires columns");
  }
  return {
    id: "",
    type: "result_view",
    schemaVersion: 1,
    title: "",
    sourceSqlArtifactId: requiredString(payload.sourceSqlArtifactId, "sourceSqlArtifactId"),
    queryFingerprint: requiredString(payload.queryFingerprint, "queryFingerprint"),
    columns: columns as ResultViewArtifact["columns"],
    datasourceGeneration:
      typeof payload.datasourceGeneration === "number"
        ? payload.datasourceGeneration
        : undefined,
    rowCount:
      typeof payload.rowCount === "number" ? payload.rowCount : undefined,
    returnedRows:
      typeof payload.returnedRows === "number" ? payload.returnedRows : undefined,
    latencyMs:
      typeof payload.latencyMs === "number" ? payload.latencyMs : undefined,
    truncated: payload.truncated === true,
  };
}

function parseChartPayload(value: unknown): ChartArtifact {
  const payload = asRecord(value);
  const chartType = requiredString(payload.chartType, "chartType");
  if (!["line", "bar", "pie", "scatter", "area"].includes(chartType)) {
    throw new Error("chart payload has an unsupported chartType");
  }
  return {
    id: "",
    type: "chart",
    schemaVersion: 1,
    title: "",
    chartType: chartType as ChartArtifact["chartType"],
    sourceResultArtifactId: requiredString(
      payload.sourceResultArtifactId,
      "sourceResultArtifactId",
    ),
    x: typeof payload.x === "string" ? payload.x : "",
    y: Array.isArray(payload.y)
      ? payload.y.filter((item): item is string => typeof item === "string")
      : [],
    aggregation:
      payload.aggregation === "sum" || payload.aggregation === "none"
        ? payload.aggregation
        : null,
  };
}

function parseMarkdownPayload(value: unknown): MarkdownArtifact {
  const payload = asRecord(value);
  const content =
    typeof payload.content === "string"
      ? payload.content
      : typeof payload.markdown === "string"
        ? payload.markdown
        : "";
  return {
    id: "",
    type: "markdown",
    schemaVersion: 1,
    title: "",
    content,
  };
}

function parseWorkspaceFileSnapshotPayload(
  value: unknown,
): WorkspaceFileSnapshotArtifact {
  const payload = asRecord(value);
  return {
    id: "",
    type: "dbfox.workspace.file_snapshot",
    schemaVersion: 1,
    title: "",
    relativePath: requiredString(payload.relativePath, "relativePath"),
    sizeBytes:
      typeof payload.sizeBytes === "number" && payload.sizeBytes >= 0
        ? payload.sizeBytes
        : 0,
    sha256: requiredString(payload.sha256, "sha256"),
    truncated: payload.truncated === true,
  };
}

function parseWorkspaceCodePatchPayload(
  value: unknown,
): WorkspaceCodePatchArtifact {
  const payload = asRecord(value);
  return {
    id: "",
    type: "dbfox.workspace.code_patch",
    schemaVersion: 1,
    title: "",
    relativePath: requiredString(payload.relativePath, "relativePath"),
    oldSha256:
      typeof payload.oldSha256 === "string" && payload.oldSha256
        ? payload.oldSha256
        : null,
    newSha256: requiredString(payload.newSha256, "newSha256"),
    sizeBytes:
      typeof payload.sizeBytes === "number" && payload.sizeBytes >= 0
        ? payload.sizeBytes
        : 0,
    created: payload.created === true,
  };
}

function parseSqlPayload(value: unknown): SqlArtifact {
  const payload = asRecord(value);
  return {
    id: "",
    type: "sql",
    schemaVersion: 1,
    title: "",
    sql: requiredString(payload.sql, "sql"),
    dialect: typeof payload.dialect === "string" ? payload.dialect : undefined,
    purpose: typeof payload.purpose === "string" ? payload.purpose : undefined,
    validationStatus:
      typeof payload.validationStatus === "string"
        ? payload.validationStatus
        : undefined,
    executionStatus:
      typeof payload.executionStatus === "string"
        ? payload.executionStatus
        : undefined,
    rowCount:
      typeof payload.rowCount === "number" ? payload.rowCount : undefined,
    latencyMs:
      typeof payload.latencyMs === "number" ? payload.latencyMs : undefined,
  };
}

const RENDERER_CONTRIBUTIONS: ReadonlyArray<
  ArtifactRendererContribution<unknown>
> = [
  {
    type: "dbfox.workspace.file_snapshot",
    supportedSchemaVersions: [1],
    parsePayload: parseWorkspaceFileSnapshotPayload,
    render: (artifact) => {
      const model = {
        ...parseWorkspaceFileSnapshotPayload(artifact.payload),
        id: artifact.id,
        title: artifact.title,
      };
      return <WorkspaceFileSnapshotArtifactView artifact={model} />;
    },
  },
  {
    type: "dbfox.workspace.code_patch",
    supportedSchemaVersions: [1],
    parsePayload: parseWorkspaceCodePatchPayload,
    render: (artifact) => {
      const model = {
        ...parseWorkspaceCodePatchPayload(artifact.payload),
        id: artifact.id,
        title: artifact.title,
      };
      return <WorkspaceCodePatchArtifactView artifact={model} />;
    },
  },
  {
    type: "result_view",
    supportedSchemaVersions: [1],
    parsePayload: parseResultViewPayload,
    render: (artifact, context) => {
      const parsed = parseResultViewPayload(artifact.payload);
      const model = { ...parsed, id: artifact.id, title: artifact.title };
      return (
        <TableArtifactView
          artifact={model}
          onToast={context.onToast}
          onOpenResultTab={context.onOpenResultTab}
          sourceSqlArtifact={context.sourceSqlArtifact}
          onOpenSqlConsole={context.onOpenSqlConsole}
          mode={context.mode ?? "inline"}
        />
      );
    },
  },
  {
    type: "chart",
    supportedSchemaVersions: [1],
    parsePayload: parseChartPayload,
    render: (artifact, context) => {
      const model = {
        ...parseChartPayload(artifact.payload),
        id: artifact.id,
        title: artifact.title,
      };
      return (
        <DeferredChartArtifactView
          artifact={model}
          onToast={context.onToast}
          compact={context.compact}
        />
      );
    },
  },
  {
    type: "markdown",
    supportedSchemaVersions: [1],
    parsePayload: parseMarkdownPayload,
    render: (artifact, context) => {
      const model = {
        ...parseMarkdownPayload(artifact.payload),
        id: artifact.id,
        title: artifact.title,
      };
      return <MarkdownArtifactView artifact={model} onToast={context.onToast} />;
    },
  },
  {
    type: "sql",
    supportedSchemaVersions: [1],
    parsePayload: parseSqlPayload,
    render: (artifact, context) => {
      if (!context.onOpenSqlConsole) {
        return (
          <ArtifactMetadataFallback
            artifact={artifact as ArtifactEnvelope}
            reason="SQL renderer requires a console action"
          />
        );
      }
      const model = {
        ...parseSqlPayload(artifact.payload),
        id: artifact.id,
        title: artifact.title,
      };
      return (
        <SqlArtifactView
          artifact={model}
          onOpenSqlConsole={context.onOpenSqlConsole}
          onToast={context.onToast}
        />
      );
    },
  },
];

const RENDERERS_BY_TYPE = new Map(
  RENDERER_CONTRIBUTIONS.map((contribution) => [contribution.type, contribution]),
);

export function getArtifactRenderer(
  type: string,
  schemaVersion = 1,
): ArtifactRendererContribution<unknown> | null {
  const contribution = RENDERERS_BY_TYPE.get(type);
  if (!contribution || !contribution.supportedSchemaVersions.includes(schemaVersion)) {
    return null;
  }
  return contribution;
}

export function ArtifactMetadataFallback({
  artifact,
  reason,
}: {
  artifact: ArtifactEnvelope;
  reason?: string;
}) {
  const schemaVersion = artifact.schema_version ?? 1;
  return (
    <ArtifactCard
      title={artifact.title}
      badge={`${artifact.type} v${schemaVersion}`}
      tone="insight"
      description={reason ?? "该工件类型尚无渲染器，仅显示元数据。"}
      meta={[
        artifact.summary ? <span key="summary">{artifact.summary}</span> : null,
        artifact.payload_ref ? (
          <span key="payloadRef">payload_ref: {artifact.payload_ref}</span>
        ) : null,
      ].filter(Boolean)}
    >
      <div className="artifact-metadata-fallback">
        <FileWarning size={16} aria-hidden="true" />
        <span>保留 Artifact envelope，不猜测 payload schema。</span>
      </div>
    </ArtifactCard>
  );
}

export function renderArtifact(
  artifact: ArtifactEnvelope,
  context: ArtifactRendererContext,
): ReactNode {
  const renderer = getArtifactRenderer(artifact.type, artifact.schema_version ?? 1);
  if (!renderer) {
    return <ArtifactMetadataFallback artifact={artifact} />;
  }
  try {
    return renderer.render(artifact, context);
  } catch {
    return <ArtifactMetadataFallback artifact={artifact} reason="payload 解析失败，已回退到元数据视图。" />;
  }
}
