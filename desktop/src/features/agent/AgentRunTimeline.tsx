import { useState } from "react";
import type { AgentArtifact, AgentRuntimeEvent, AgentStep, AgentTaskLens } from "./types";
import { AgentTaskLensPanel } from "./AgentTaskLens";
import { stepDisplayName } from "./stepDisplayNames";

type TimelineStatus = "running" | "success" | "blocked" | "failed" | "skipped";

type TimelineAction = "open_sql" | "open_artifact" | "none";

interface TimelineEntry {
  id: string;
  label: string;
  status: TimelineStatus;
  detail?: string | null;
  technicalName?: string;
  latencyMs?: number | null;
  artifactId?: string | null;
  action: TimelineAction;
  actionTitle?: string;
  source: "progress" | "step" | "artifact";
}

interface AgentRunTimelineProps {
  steps: AgentStep[];
  runtimeEvents?: AgentRuntimeEvent[];
  artifacts?: AgentArtifact[];
  contextSummary?: string | null;
  taskLens?: AgentTaskLens | null;
  onOpenArtifact?: (artifactId: string) => void;
  onOpenSql?: (sql: string) => void;
  defaultExpanded?: boolean;
}

const STEP_ARTIFACT_TYPES: Record<string, string[]> = {
  build_query_plan: ["query_plan"],
  generate_sql_candidate: ["query_plan", "sql"],
  validate_sql: ["sql", "safety"],
  execute_sql: ["table"],
  profile_result: ["insight"],
  suggest_chart: ["chart"],
  revise_sql: ["sql_suggestion", "sql"],
};

export function AgentRunTimeline({
  steps,
  runtimeEvents = [],
  artifacts = [],
  contextSummary,
  taskLens,
  onOpenArtifact,
  onOpenSql,
  defaultExpanded = true,
}: AgentRunTimelineProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [showTechnical, setShowTechnical] = useState(false);

  const entries = buildRunTimeline(steps, runtimeEvents, artifacts);
  if (!entries.length && !contextSummary && !taskLens) return null;

  const toggle = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const runningCount = entries.filter((e) => e.status === "running").length;
  const doneCount = entries.filter((e) => e.status === "success").length;

  return (
    <section
      style={{
        padding: "8px 10px",
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-light)",
        borderRadius: 6,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <strong style={{ fontSize: "0.66rem" }}>Agent run</strong>
        <span style={{ color: "var(--text-muted)", fontSize: "0.6rem", whiteSpace: "nowrap" }}>
          {doneCount} done{runningCount ? ` · ${runningCount} in progress` : ""}
        </span>
      </div>

      <AgentTaskLensPanel taskLens={taskLens} compact />
      {contextSummary ? (
        <div style={{ marginTop: 5, fontSize: "0.58rem", color: "var(--text-muted)" }}>
          {contextSummary}
        </div>
      ) : null}

      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
        {entries.map((entry) => {
          const isOpen = defaultExpanded || expandedIds.has(entry.id);
          const hasDetail = Boolean(entry.detail || entry.technicalName);
          const labelNode = entry.action !== "none" && entry.artifactId ? (
            <button
              type="button"
              onClick={() => handleTimelineEntryClick(entry, artifacts, onOpenSql, onOpenArtifact)}
              style={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                fontSize: "0.64rem",
                border: "none",
                background: "none",
                padding: 0,
                color: "var(--accent-primary)",
                cursor: "pointer",
                textAlign: "left",
                fontWeight: 500,
              }}
              title={entry.actionTitle || entry.label}
            >
              {entry.label}
            </button>
          ) : (
            <span
              style={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                fontSize: "0.64rem",
              }}
              title={entry.label}
            >
              {entry.label}
            </span>
          );

          return (
            <div key={entry.id} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "14px minmax(0, 1fr) auto",
                  alignItems: "center",
                  gap: 6,
                  minHeight: 22,
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: 7,
                    background: statusColor(entry.status),
                    justifySelf: "center",
                  }}
                />
                {labelNode}
                <span
                  className={`inline-flex items-center px-1.5 py-0.5 text-xs font-semibold rounded-sm ${statusClass(entry.status)}`}
                  style={{ fontSize: "0.56rem" }}
                >
                  {entry.status}
                </span>
              </div>

              {hasDetail && isOpen ? (
                <div style={{ marginLeft: 20, fontSize: "0.58rem", color: "var(--text-muted)", lineHeight: 1.4 }}>
                  {entry.detail ? <div>{entry.detail}</div> : null}
                  {showTechnical && entry.technicalName ? (
                    <div style={{ marginTop: 2, fontFamily: "monospace" }}>{entry.technicalName}</div>
                  ) : null}
                  {entry.latencyMs != null ? <div>{entry.latencyMs}ms</div> : null}
                </div>
              ) : null}

              {hasDetail ? (
                <button
                  type="button"
                  onClick={() => toggle(entry.id)}
                  style={{
                    marginLeft: 20,
                    alignSelf: "flex-start",
                    border: "none",
                    background: "none",
                    color: "var(--text-muted)",
                    fontSize: "0.56rem",
                    cursor: "pointer",
                    padding: 0,
                  }}
                >
                  {isOpen ? "Hide detail" : "Show detail"}
                </button>
              ) : null}
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={() => setShowTechnical((v) => !v)}
        style={{
          marginTop: 6,
          border: "none",
          background: "none",
          color: "var(--text-muted)",
          fontSize: "0.56rem",
          cursor: "pointer",
          padding: 0,
        }}
      >
        {showTechnical ? "Hide technical names" : "Developer: show technical names"}
      </button>
    </section>
  );
}

function buildRunTimeline(
  steps: AgentStep[],
  runtimeEvents: AgentRuntimeEvent[],
  artifacts: AgentArtifact[],
): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  const indexByKey = new Map<string, number>();
  const assignedArtifactIds = new Set<string>();
  const artifactsByType = groupArtifactsByType(artifacts);

  const upsert = (key: string, entry: TimelineEntry) => {
    const existing = indexByKey.get(key);
    if (existing === undefined) {
      indexByKey.set(key, entries.length);
      entries.push(entry);
      return;
    }
    entries[existing] = { ...entries[existing], ...entry };
  };

  const sorted = [...runtimeEvents].sort((a, b) => (a.sequence || 0) - (b.sequence || 0));

  for (const event of sorted) {
    if (event.type === "agent.artifact.created" && event.artifact) {
      const art = event.artifact;
      const key = `artifact:${art.id}`;
      const action = resolveArtifactAction(art);
      upsert(key, {
        id: key,
        label: artifactTimelineLabel(art),
        status: "success",
        artifactId: art.id,
        technicalName: art.type,
        action: action.action,
        actionTitle: action.title,
        source: "artifact",
      });
      assignedArtifactIds.add(art.id);
      continue;
    }

    if (event.type === "agent.progress.update") {
      const step = event.step || {};
      const summary = typeof step.summary === "string" ? step.summary : "";
      if (!summary) continue;
      const key = `progress:${summary}`;
      upsert(key, {
        id: key,
        label: summary,
        status: mapProgressStatus(step.status),
        detail: typeof step.detail === "string" ? step.detail : null,
        technicalName: typeof step.name === "string" ? step.name : undefined,
        action: "none",
        source: "progress",
      });
      continue;
    }

    if (event.type === "agent.step.started") {
      const name = typeof event.step?.name === "string" ? event.step.name : "";
      if (!name) continue;
      upsert(`step:${name}`, {
        id: `step:${name}`,
        label: stepDisplayName(name),
        status: "running",
        technicalName: name,
        action: "none",
        source: "step",
      });
      continue;
    }

    if (event.type === "agent.step.completed") {
      const name = typeof event.step?.name === "string" ? event.step.name : "";
      if (!name) continue;
      const artifactId = typeof event.step?.artifact_id === "string"
        ? event.step.artifact_id
        : resolveArtifactForStep(name, artifactsByType, assignedArtifactIds);
      if (artifactId) assignedArtifactIds.add(artifactId);

      const summary = typeof event.step?.summary === "string" ? event.step.summary : null;
      const key = artifactId ? `artifact:${artifactId}` : `step:${name}`;
      const linkedArt = artifactId ? artifacts.find((item) => item.id === artifactId) : undefined;
      const action = linkedArt ? resolveArtifactAction(linkedArt) : { action: "none" as TimelineAction, title: undefined };
      upsert(key, {
        id: key,
        label: linkedArt ? artifactTimelineLabel(linkedArt) : (summary || stepDisplayName(name)),
        status: mapStepStatus(event.step?.status),
        technicalName: name,
        latencyMs: typeof event.step?.latency_ms === "number" ? event.step.latency_ms : null,
        detail: typeof event.step?.error === "string" ? event.step.error : null,
        artifactId,
        action: artifactId ? action.action : "none",
        actionTitle: action.title,
        source: "step",
      });
    }
  }

  if (!entries.length) {
    for (const step of steps) {
      const artifactId = resolveArtifactForStep(step.name, artifactsByType, assignedArtifactIds);
      if (artifactId) assignedArtifactIds.add(artifactId);
      const linkedArt = artifactId ? artifacts.find((item) => item.id === artifactId) : undefined;
      const action = linkedArt ? resolveArtifactAction(linkedArt) : { action: "none" as TimelineAction, title: undefined };
      upsert(`step:${step.name}`, {
        id: `step:${step.name}`,
        label: linkedArt ? artifactTimelineLabel(linkedArt) : stepDisplayName(step.name),
        status: mapStepStatus(step.status),
        technicalName: step.name,
        latencyMs: step.latency_ms,
        detail: step.error,
        artifactId,
        action: artifactId ? action.action : "none",
        actionTitle: action.title,
        source: "step",
      });
    }
  }

  return entries;
}

function groupArtifactsByType(artifacts: AgentArtifact[]): Map<string, AgentArtifact[]> {
  const map = new Map<string, AgentArtifact[]>();
  for (const art of artifacts) {
    const list = map.get(art.type) || [];
    list.push(art);
    map.set(art.type, list);
  }
  return map;
}

function resolveArtifactForStep(
  stepName: string,
  artifactsByType: Map<string, AgentArtifact[]>,
  assigned: Set<string>,
): string | null {
  const types = STEP_ARTIFACT_TYPES[stepName] || [];
  for (const type of types) {
    const candidates = artifactsByType.get(type) || [];
    for (const art of candidates) {
      if (!assigned.has(art.id)) return art.id;
    }
  }
  return null;
}

function handleTimelineEntryClick(
  entry: TimelineEntry,
  artifacts: AgentArtifact[],
  onOpenSql?: (sql: string) => void,
  onOpenArtifact?: (artifactId: string) => void,
) {
  if (!entry.artifactId) return;
  const artifact = artifacts.find((item) => item.id === entry.artifactId);
  if (entry.action === "open_sql") {
    const sql = artifact ? extractSqlFromArtifact(artifact) : null;
    if (sql && onOpenSql) {
      onOpenSql(sql);
      return;
    }
  }
  onOpenArtifact?.(entry.artifactId);
}

function artifactTimelineLabel(artifact: AgentArtifact): string {
  if (artifact.type === "chart") {
    const chartType = String(artifact.payload?.type || "chart");
    const x = String(artifact.payload?.x || "");
    const y = String(artifact.payload?.y || "");
    if (x && y) return `Chart: ${chartType} (${x} × ${y})`;
    return `Chart: ${chartType}`;
  }
  if (artifact.type === "table") {
    const rows = artifact.payload?.rowCount;
    return rows !== undefined ? `${artifact.title} (${rows} rows)` : artifact.title;
  }
  return artifact.title || artifact.type;
}

function resolveArtifactAction(artifact: AgentArtifact): { action: TimelineAction; title?: string } {
  if (extractSqlFromArtifact(artifact)) {
    return { action: "open_sql", title: `Open SQL in editor — ${artifact.title}` };
  }
  if (artifact.type === "chart") {
    return { action: "open_artifact", title: `View chart suggestion — ${artifact.title}` };
  }
  if (artifact.type === "table" || artifact.type === "insight") {
    return { action: "open_artifact", title: `View result — ${artifact.title}` };
  }
  return { action: "open_artifact", title: `Inspect ${artifact.title}` };
}

function extractSqlFromArtifact(artifact: AgentArtifact): string | null {
  const payload = artifact.payload || {};
  if (typeof payload.sql === "string" && payload.sql.trim()) {
    return payload.sql;
  }
  if (typeof payload.revised_sql === "string" && payload.revised_sql.trim()) {
    return payload.revised_sql;
  }
  if (typeof payload.suggested_sql === "string" && payload.suggested_sql.trim()) {
    return payload.suggested_sql;
  }
  return null;
}

function mapProgressStatus(value: unknown): TimelineStatus {
  if (value === "complete" || value === "success") return "success";
  if (value === "failed") return "failed";
  if (value === "blocked" || value === "clarify") return "blocked";
  return "running";
}

function mapStepStatus(value: unknown): TimelineStatus {
  if (value === "failed") return "failed";
  if (value === "skipped") return "skipped";
  if (value === "running") return "running";
  return "success";
}

function statusClass(status: TimelineStatus) {
  if (status === "failed") return "bg-destructive/15 text-destructive";
  if (status === "running") return "bg-primary/10 text-primary";
  if (status === "blocked") return "bg-secondary text-secondary-foreground";
  if (status === "skipped") return "bg-secondary text-secondary-foreground";
  return "bg-success/15 text-success";
}

function statusColor(status: TimelineStatus) {
  if (status === "failed") return "var(--accent-red)";
  if (status === "running") return "var(--accent-primary)";
  if (status === "blocked") return "var(--text-muted)";
  if (status === "skipped") return "var(--text-muted)";
  return "var(--accent-green)";
}
