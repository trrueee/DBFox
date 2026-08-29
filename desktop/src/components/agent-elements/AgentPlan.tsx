/*
 * Production replacement based on Agent Elements' MIT-licensed PlanTool and
 * TodoTool registry sources:
 * https://agent-elements.21st.dev/r/plan-tool.json
 * https://agent-elements.21st.dev/r/todo-tool.json
 *
 * The component consumes DBFox's authoritative PlanItem directly. Agent
 * Elements' AI SDK `part` model is intentionally not copied or mirrored.
 * Lucide replaces Tabler to keep the application's existing icon system.
 *
 * Presentation: objective + progress + a plain checklist. No file names,
 * progress bars, or status legends — the step glyphs carry that meaning.
 */
import { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronUp,
  Circle,
  CircleStop,
  LoaderCircle,
  X,
} from "lucide-react";

import type { ConversationArtifact, PlanItem } from "../../types/conversation";
import { cn } from "../../lib/utils";
import { Button } from "../ui";

type PlanStep = PlanItem["payload"]["steps"][number];

export function AgentPlan({
  item,
  artifacts,
  onSelectArtifact,
}: {
  item: PlanItem;
  artifacts?: readonly ConversationArtifact[];
  onSelectArtifact?: (artifactId: string) => void;
}) {
  const running = item.status === "in_progress" || item.status === "pending";
  const needsAttention = item.status === "waiting" || item.status === "failed";
  const disclosureKey = `${item.id}:${item.status}`;
  const autoExpanded = running || needsAttention;
  const [disclosure, setDisclosure] = useState({ key: disclosureKey, expanded: autoExpanded });
  const expanded = disclosure.key === disclosureKey ? disclosure.expanded : autoExpanded;
  const contentId = `agent-plan-${item.id}`;
  const totalSteps = item.payload.steps.length;
  const completedSteps = item.payload.steps.filter((step) => step.status === "completed").length;

  return (
    <section className="my-1" data-status={item.status} aria-label="执行计划">
      <button
        type="button"
        onClick={() => setDisclosure({ key: disclosureKey, expanded: !expanded })}
        aria-controls={contentId}
        aria-expanded={expanded}
        className="grid min-h-7 w-full grid-cols-[20px_minmax(0,1fr)_auto_auto] items-center gap-2 rounded-[var(--radius-row)] px-1 text-left hover:bg-[var(--control-bg-hover)] focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
      >
        <span className="inline-grid size-4 place-items-center text-[var(--agent-text-muted)]" aria-hidden="true">
          <PlanStatusIcon status={item.status} />
        </span>
        <span className="truncate text-sm text-[var(--agent-text-secondary)]">
          {item.payload.objective || "执行计划"}
        </span>
        <span className="shrink-0 text-xs tabular-nums text-[var(--agent-text-muted)]">
          {completedSteps}/{totalSteps}
        </span>
        <span className="inline-grid size-4 place-items-center text-[var(--agent-text-muted)]">
          {expanded ? <ChevronUp className="size-4" aria-hidden="true" /> : <ChevronDown className="size-4" aria-hidden="true" />}
        </span>
      </button>

      <ol
        id={contentId}
        hidden={!expanded}
        className="ml-[9px] grid list-none gap-1.5 border-l border-[var(--hairline)] py-1 pl-3"
      >
        {item.payload.steps.map((step) => (
          <PlanStepRow
            key={step.id}
            step={step}
            running={running}
            artifacts={artifacts}
            onSelectArtifact={onSelectArtifact}
          />
        ))}
      </ol>
    </section>
  );
}

function PlanStepRow({
  step,
  running,
  artifacts,
  onSelectArtifact,
}: {
  step: PlanStep;
  running: boolean;
  artifacts?: readonly ConversationArtifact[];
  onSelectArtifact?: (artifactId: string) => void;
}) {
  const artifactIds = step.artifact_ids ?? [];
  const availableArtifacts = artifacts?.filter(
    (artifact) => artifact.status === "completed" && artifactIds.includes(artifact.id),
  ) ?? [];
  const missingEvidence = artifacts !== undefined
    && step.status === "completed"
    && Boolean(step.evidence_required)
    && (artifactIds.length === 0 || availableArtifacts.length < artifactIds.length);

  return (
    <li
      className="grid grid-cols-[16px_minmax(0,1fr)] items-start gap-2 py-0.5"
      data-status={step.status}
      aria-current={step.status === "in_progress" ? "step" : undefined}
    >
      <span className="mt-0.5 inline-grid size-4 place-items-center" aria-hidden="true">
        <PlanStepIcon status={step.status} running={running} />
      </span>
      <span className="min-w-0">
        <span
          className={cn(
            "block text-sm leading-5",
            step.status === "completed" && "text-[var(--agent-text-muted)] line-through",
            step.status === "blocked" && "text-[var(--color-warning)]",
            step.status === "skipped" && "text-[var(--agent-text-muted)]",
          )}
        >
          {step.title}
        </span>
        {step.note ? <small className="block text-xs leading-5 text-[var(--agent-text-muted)]">{step.note}</small> : null}
        {availableArtifacts.length > 0 || missingEvidence ? (
          <span className="mt-1 flex flex-wrap items-center gap-1.5">
            {availableArtifacts.map((artifact) => (
              <Button
                key={artifact.id}
                type="button"
                variant="outline"
                size="sm"
                className="h-7 max-w-full px-2 text-xs"
                onClick={() => onSelectArtifact?.(artifact.id)}
                disabled={!onSelectArtifact}
                aria-label={`打开完成证据：${artifact.title}`}
              >
                <span className="truncate">{artifact.title}</span>
              </Button>
            ))}
            {missingEvidence ? (
              <small className="text-xs leading-5 text-[var(--color-warning)]">完成证据暂不可用</small>
            ) : null}
          </span>
        ) : null}
        <span className="sr-only">{planStepStatusLabel(step.status)}</span>
      </span>
    </li>
  );
}

function PlanStatusIcon({ status }: { status: PlanItem["status"] }) {
  if (status === "pending" || status === "in_progress") {
    return <LoaderCircle className="size-3.5 shrink-0 animate-spin text-[var(--agent-accent)]" aria-hidden="true" />;
  }
  if (status === "waiting") {
    return <AlertTriangle className="size-3.5 shrink-0 text-[var(--color-warning)]" aria-hidden="true" />;
  }
  if (status === "failed") {
    return <AlertTriangle className="size-3.5 shrink-0 text-[var(--color-danger)]" aria-hidden="true" />;
  }
  if (status === "cancelled") {
    return <CircleStop className="size-3.5 shrink-0 text-[var(--agent-text-muted)]" aria-hidden="true" />;
  }
  if (status === "completed") {
    return <Check className="size-3.5 shrink-0 text-[var(--color-success)]" aria-hidden="true" />;
  }
  return <Circle className="size-3.5 shrink-0 text-[var(--agent-text-muted)]" aria-hidden="true" />;
}

function PlanStepIcon({ status, running }: { status: PlanStep["status"]; running: boolean }) {
  if (status === "in_progress") {
    return running
      ? <LoaderCircle className="size-3.5 animate-spin text-[var(--agent-accent)]" />
      : <ArrowRight className="size-3.5 text-[var(--agent-accent)]" />;
  }
  if (status === "completed") return <Check className="size-3.5 text-[var(--color-success)]" />;
  if (status === "blocked") return <AlertTriangle className="size-3.5 text-[var(--color-warning)]" />;
  if (status === "skipped") return <X className="size-3.5 text-[var(--agent-text-muted)]" />;
  return <Circle className="size-3.5 text-[var(--agent-text-muted)]" />;
}

function planStepStatusLabel(status: PlanStep["status"]) {
  if (status === "in_progress") return "进行中";
  if (status === "completed") return "已完成";
  if (status === "blocked") return "受阻";
  if (status === "skipped") return "已跳过";
  return "待处理";
}
