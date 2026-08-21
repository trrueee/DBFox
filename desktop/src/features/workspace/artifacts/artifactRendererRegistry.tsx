import type { ReactNode } from "react";
import { FileWarning } from "lucide-react";
import { ArtifactCard } from "./ArtifactCard";
import { coreArtifactRenderers } from "./coreArtifactRenderers";
import {
  createDataArtifactRenderers,
  dataArtifactRenderers,
  type DataArtifactRendererActions,
} from "./dataArtifactRenderers";
import { workspaceArtifactRenderers } from "./workspaceArtifactRenderers";
import type {
  ArtifactEnvelope,
  ArtifactRendererContext,
  ArtifactRendererContribution,
} from "./types";
import { useDlcStore } from "../../dlc/extensionStore";

export type {
  ArtifactEnvelope,
  ArtifactRendererContext,
  ArtifactRendererContribution,
  DataArtifactRendererActions,
};

export {
  coreArtifactRenderers,
  createDataArtifactRenderers,
  dataArtifactRenderers,
  workspaceArtifactRenderers,
};

export interface ArtifactRendererRegistry {
  get: (type: string, schemaVersion?: number) => ArtifactRendererContribution<unknown> | null;
  all: () => readonly ArtifactRendererContribution<unknown>[];
}

export function createArtifactRendererRegistry(
  contributions: readonly ArtifactRendererContribution<unknown>[],
): ArtifactRendererRegistry {
  const map = new Map<string, ArtifactRendererContribution<unknown>>();
  for (const contribution of contributions) {
    if (map.has(contribution.type)) {
      throw new Error(
        `Duplicate Artifact renderer contribution detected: "${contribution.type}". Registration must fail closed.`,
      );
    }
    map.set(contribution.type, contribution);
  }
  return {
    get: (type: string, schemaVersion = 1) => {
      const contribution = map.get(type);
      if (!contribution || !contribution.supportedSchemaVersions.includes(schemaVersion)) {
        return null;
      }
      return contribution;
    },
    all: () => contributions,
  };
}

export function productArtifactRenderers(options?: {
  dataActions?: DataArtifactRendererActions;
}): readonly ArtifactRendererContribution<unknown>[] {
  return [
    ...coreArtifactRenderers,
    ...(options?.dataActions
      ? createDataArtifactRenderers(options.dataActions)
      : dataArtifactRenderers),
    ...workspaceArtifactRenderers,
  ];
}

export const DEFAULT_ARTIFACT_RENDERER_REGISTRY = createArtifactRendererRegistry(
  productArtifactRenderers(),
);

export function getArtifactRenderer(
  type: string,
  schemaVersion = 1,
  registry: ArtifactRendererRegistry = DEFAULT_ARTIFACT_RENDERER_REGISTRY,
): ArtifactRendererContribution<unknown> | null {
  const result = registry.get(type, schemaVersion);
  if (result) return result;

  const dlcRenderers = useDlcStore.getState().contributions.artifactRenderers;
  const dlcRenderer = dlcRenderers.find(
    (r) => r.type === type && r.supportedSchemaVersions.includes(schemaVersion),
  );
  return dlcRenderer ?? null;
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
  registry: ArtifactRendererRegistry = DEFAULT_ARTIFACT_RENDERER_REGISTRY,
): ReactNode {
  const renderer = getArtifactRenderer(artifact.type, artifact.schema_version ?? 1, registry);
  if (!renderer) {
    return <ArtifactMetadataFallback artifact={artifact} />;
  }
  try {
    return renderer.render(artifact, context);
  } catch {
    return (
      <ArtifactMetadataFallback
        artifact={artifact}
        reason="payload 解析失败，已回退到元数据视图。"
      />
    );
  }
}
