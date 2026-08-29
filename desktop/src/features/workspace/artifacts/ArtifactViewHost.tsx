import { useEffect, useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { Button, Spinner, Tabs, TabsContent, TabsList, TabsTrigger } from "../../../components/ui";
import { agentApi } from "../../../lib/api/agent";
import { getUserErrorMessage } from "../../../lib/api/client";
import { useDlcStore } from "../../dlc/extensionStore";
import { ArtifactCard } from "./ArtifactCard";
import {
  createArtifactViewRegistry,
  matchingArtifactViews,
  productArtifactViews,
} from "./artifactViewRegistry";
import type {
  ArtifactEnvelope,
  ArtifactRepresentationAccess,
  ArtifactRepresentationDescriptor,
  ArtifactViewContext,
  ArtifactViewContribution,
  ArtifactViewSurface,
} from "./types";
import "./ArtifactViews.css";

interface ArtifactViewHostProps {
  artifact: ArtifactEnvelope<unknown>;
  surface: ArtifactViewSurface;
  onToast: (message: string) => void;
  compact?: boolean;
  selectedViewId?: string;
  onSelectedViewChange?: (viewId: string) => void;
  resolveArtifact?: ArtifactViewContext["resolveArtifact"];
  openArtifact?: ArtifactViewContext["openArtifact"];
}

export function ArtifactViewHost({
  artifact,
  surface,
  onToast,
  compact,
  selectedViewId,
  onSelectedViewChange,
  resolveArtifact,
  openArtifact,
}: ArtifactViewHostProps) {
  const dlcViews = useDlcStore((state) => state.contributions.artifactViews);
  const registry = useMemo(
    () => createArtifactViewRegistry([...productArtifactViews(), ...dlcViews]),
    [dlcViews],
  );
  const canDiscoverRepresentations = artifact.status === undefined || artifact.status === "completed";
  const discovery = useArtifactRepresentations(
    artifact.id,
    artifact.version ?? 0,
    canDiscoverRepresentations,
  );
  const representations = discovery.representations;
  const representationAccess = useMemo<ArtifactRepresentationAccess>(() => ({
    available: representations,
    list: (artifactId, signal) => agentApi.listArtifactRepresentations(artifactId, signal),
    read: (artifactId, representationType, request, signal) => (
      agentApi.readArtifactRepresentation(artifactId, representationType, request, signal)
    ),
    stream: (artifactId, representationType, request, signal) => (
      agentApi.streamArtifactRepresentation(artifactId, representationType, request, signal)
    ),
  }), [representations]);
  const views = useMemo(
    () => matchingArtifactViews(artifact, representations, surface, registry.all()),
    [artifact, registry, representations, surface],
  );
  const [localSelection, setLocalSelection] = useState<{ artifactId: string; viewId: string } | null>(null);
  const requestedViewId = selectedViewId
    ?? (localSelection?.artifactId === artifact.id ? localSelection.viewId : undefined);
  const selectedView = views.find((view) => view.id === requestedViewId) ?? views[0] ?? null;

  useEffect(() => {
    if (discovery.status !== "loading" && selectedView && selectedView.id !== requestedViewId) {
      onSelectedViewChange?.(selectedView.id);
    }
  }, [discovery.status, onSelectedViewChange, requestedViewId, selectedView]);

  if (discovery.status === "loading" && views.length === 0) {
    return (
      <div className="artifact-view-host__loading" role="status">
        <Spinner aria-hidden="true" />
        <span>正在发现可用视图</span>
      </div>
    );
  }

  if (!selectedView) {
    return (
      <ArtifactMetadataFallback
        artifact={artifact}
        reason={discovery.error
          ? getUserErrorMessage(discovery.error, "无法发现该工件的可用视图。")
          : undefined}
      />
    );
  }

  const context: ArtifactViewContext = {
    onToast,
    compact,
    surface,
    representations: representationAccess,
    resolveArtifact,
    openArtifact,
  };

  if (surface !== "workspace" || views.length === 1) {
    const rendered = renderView(selectedView, artifact, context);
    if (surface === "inline" && openArtifact) {
      return (
        <div className="artifact-view-host__inline">
          {rendered}
          <div className="artifact-view-host__inline-actions">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => openArtifact(artifact)}
            >
              <ExternalLink size={14} aria-hidden="true" />
              在工作区查看
            </Button>
          </div>
        </div>
      );
    }
    return rendered;
  }

  return (
    <Tabs
      className="artifact-view-host"
      value={selectedView.id}
      onValueChange={(viewId) => {
        setLocalSelection({ artifactId: artifact.id, viewId });
        onSelectedViewChange?.(viewId);
      }}
    >
      <div className="artifact-view-host__bar">
        <TabsList aria-label="工件视图">
          {views.map((view) => (
            <TabsTrigger key={view.id} value={view.id}>
              {view.title}
            </TabsTrigger>
          ))}
        </TabsList>
        {discovery.error ? (
          <span className="artifact-view-host__discovery-warning">部分视图不可用</span>
        ) : null}
      </div>
      {views.map((view) => (
        <TabsContent key={view.id} value={view.id} className="artifact-view-host__content">
          {view.id === selectedView.id ? renderView(view, artifact, context) : null}
        </TabsContent>
      ))}
    </Tabs>
  );
}

function useArtifactRepresentations(
  artifactId: string,
  artifactVersion: number,
  enabled: boolean,
): {
  status: "idle" | "loading" | "ready" | "error";
  representations: readonly ArtifactRepresentationDescriptor[];
  error: unknown | null;
} {
  const [state, setState] = useState<{
    key: string;
    status: "idle" | "loading" | "ready" | "error";
    representations: readonly ArtifactRepresentationDescriptor[];
    error: unknown | null;
  }>({ key: "", status: "idle", representations: [], error: null });
  const key = `${artifactId}:${artifactVersion}`;

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    const controller = new AbortController();
    void agentApi.listArtifactRepresentations(artifactId, controller.signal).then(
      (representations) => {
        if (!controller.signal.aborted) {
          setState({ key, status: "ready", representations, error: null });
        }
      },
      (error) => {
        if (!controller.signal.aborted) {
          setState({ key, status: "error", representations: [], error });
        }
      },
    );
    return () => controller.abort();
  }, [artifactId, artifactVersion, enabled, key]);

  if (!enabled) {
    return { status: "idle", representations: [], error: null };
  }
  return state.key === key
    ? state
    : { status: "loading", representations: [], error: null };
}

function renderView(
  view: ArtifactViewContribution<unknown>,
  artifact: ArtifactEnvelope<unknown>,
  context: ArtifactViewContext,
) {
  try {
    const payload = view.parsePayload(artifact.payload);
    return view.render(artifact, payload, context);
  } catch {
    return (
      <ArtifactMetadataFallback
        artifact={artifact}
        reason={`“${view.title}”无法解析该工件，已保留元数据。`}
      />
    );
  }
}

function ArtifactMetadataFallback({
  artifact,
  reason,
}: {
  artifact: ArtifactEnvelope<unknown>;
  reason?: string;
}) {
  return (
    <ArtifactCard
      title={artifact.title}
      badge={`${artifact.type} v${artifact.schema_version ?? 1}`}
      tone="insight"
      description={reason ?? "暂无可用视图。"}
      meta={artifact.summary ? <span>{artifact.summary}</span> : undefined}
    />
  );
}
