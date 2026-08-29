/*
 * Production replacement based on Agent Elements' MIT-licensed ToolGroup,
 * ToolRowBase, and GenericTool registry sources:
 * https://agent-elements.21st.dev/r/tool-group.json
 * https://agent-elements.21st.dev/docs/tool-group
 *
 * DBFox FunctionCallItem/FunctionCallOutputItem remain the only data model.
 * The upstream AI SDK `part`, tool registry, and simulated streaming state are
 * intentionally not copied. Actual durable timeline items drive the list.
 *
 * Presentation follows the quiet activity-row language: no cards or borders —
 * one muted row (icon · title · status · duration) that expands into an
 * indented detail block.
 */
import { memo, useEffect, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  Check,
  ChevronDown,
  CircleStop,
  Clock3,
  FileOutput,
  LoaderCircle,
  Search,
  Settings2,
  TerminalSquare,
} from "lucide-react";

import type {
  ConversationRun,
  ConversationRunItem,
  FunctionCallItem,
  FunctionCallOutputItem,
} from "../../types/conversation";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";

type ToolGroup = {
  id: string;
  title: string;
  category: FunctionCallItem["payload"]["presentation"]["category"];
  items: FunctionCallItem[];
};

type SharedProps = {
  outputs: ReadonlyMap<string, FunctionCallOutputItem>;
  runStatus: ConversationRun["status"];
  onSelectArtifact?: (artifactId: string) => void;
};

export const AgentTool = memo(function AgentTool({
  item,
  output,
  runStatus,
  onSelectArtifact,
}: {
  item: FunctionCallItem;
  output?: FunctionCallOutputItem;
  runStatus: ConversationRun["status"];
  onSelectArtifact?: (artifactId: string) => void;
}) {
  if (item.payload.presentation.visibility === "developer") return null;
  const status = output?.status || item.status;
  const live = status === "in_progress" || status === "pending";
  const detailId = `agent-tool-${item.id}`;

  return (
    <ToolFrame
      identity={item.id}
      contentId={detailId}
      title={item.payload.presentation.title}
      status={status}
      runStatus={runStatus}
      category={item.payload.presentation.category}
      live={live}
      elapsed={toolElapsed([item], output ? [output] : [])}
    >
      <ToolItem
        item={item}
        output={output}
        runStatus={runStatus}
        showStatus={false}
        onSelectArtifact={onSelectArtifact}
      />
    </ToolFrame>
  );
});

export const AgentToolGroup = memo(function AgentToolGroup({
  group,
  outputs,
  runStatus,
  onSelectArtifact,
}: { group: ToolGroup } & SharedProps) {
  const statuses = group.items.map((item) => outputs.get(item.payload.call_id)?.status || item.status);
  const status = groupStatus(statuses);
  const live = status === "in_progress" || status === "pending";
  const detailId = `agent-tool-group-${group.id}`;
  const groupOutputs = group.items.flatMap((item) => {
    const output = outputs.get(item.payload.call_id);
    return output ? [output] : [];
  });

  return (
    <ToolFrame
      identity={group.id}
      contentId={detailId}
      title={group.title}
      detail={` ${group.items.length} 次调用`}
      status={status}
      runStatus={runStatus}
      category={group.category}
      live={live}
      elapsed={toolElapsed(group.items, groupOutputs)}
      boundedList={live && group.items.length > 5}
    >
      <div className="grid gap-2">
        {group.items.map((item, index) => (
          <ToolItem
            key={item.id}
            item={item}
            output={outputs.get(item.payload.call_id)}
            runStatus={runStatus}
            index={index}
            onSelectArtifact={onSelectArtifact}
          />
        ))}
      </div>
    </ToolFrame>
  );
});

function ToolFrame({
  identity,
  contentId,
  title,
  detail,
  status,
  runStatus,
  category,
  live,
  elapsed,
  boundedList = false,
  children,
}: {
  identity: string;
  contentId: string;
  title: string;
  detail?: string;
  status: ConversationRunItem["status"];
  runStatus: ConversationRun["status"];
  category: FunctionCallItem["payload"]["presentation"]["category"];
  live: boolean;
  elapsed: { startedAt: number | null; completedMs: number | null };
  boundedList?: boolean;
  children: ReactNode;
}) {
  const disclosureKey = `${identity}:${live ? "live" : "settled"}`;
  const [disclosure, setDisclosure] = useState({ key: disclosureKey, expanded: live });
  const expanded = disclosure.key === disclosureKey ? disclosure.expanded : live;
  const elapsedLabel = useElapsedLabel(elapsed.startedAt, elapsed.completedMs, live);

  return (
    <section className="my-0.5" data-status={status}>
      <button
        type="button"
        className="grid min-h-7 w-full grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-2 rounded-[var(--radius-row)] px-1 text-left hover:bg-[var(--control-bg-hover)] focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
        aria-controls={contentId}
        aria-expanded={expanded}
        onClick={() => setDisclosure({ key: disclosureKey, expanded: !expanded })}
      >
        <span
          className="inline-grid size-4 place-items-center text-[var(--agent-text-muted)]"
          title={toolCategoryLabel(category)}
          aria-hidden="true"
        >
          <ToolCategoryIcon category={category} />
        </span>
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="truncate text-sm text-[var(--agent-text-secondary)]">{title}</span>
          {detail ? (
            <span className="shrink-0 text-xs text-[var(--agent-text-muted)]">·{detail}</span>
          ) : null}
          <ToolStatus status={status} runStatus={runStatus} />
        </span>
        <span className="flex items-center gap-1.5 text-xs tabular-nums text-[var(--agent-text-muted)]">
          {elapsedLabel ? <span>{elapsedLabel}</span> : null}
          <ChevronDown
            className={cn("size-4 transition-transform", expanded && "rotate-180")}
            aria-hidden="true"
          />
        </span>
      </button>
      <div
        id={contentId}
        hidden={!expanded}
        className={cn(
          "ml-[9px] border-l border-[var(--hairline)] py-1 pl-3",
          boundedList && "max-h-[140px] overflow-y-auto [scrollbar-gutter:stable]",
        )}
      >
        {children}
      </div>
    </section>
  );
}

function ToolItem({
  item,
  output,
  runStatus,
  index,
  showStatus = true,
  onSelectArtifact,
}: {
  item: FunctionCallItem;
  output?: FunctionCallOutputItem;
  runStatus: ConversationRun["status"];
  index?: number;
  showStatus?: boolean;
  onSelectArtifact?: (artifactId: string) => void;
}) {
  const status = output?.status || item.status;
  return (
    <article className="grid gap-2 py-1 text-sm">
      <header className="flex flex-wrap items-center gap-2 text-xs text-[var(--agent-text-muted)]">
        {index !== undefined ? <span className="tabular-nums">#{index + 1}</span> : null}
        <code className="min-w-0 break-all font-[var(--font-family-code)] text-[var(--agent-text-secondary)]">
          {item.payload.name}
        </code>
        {item.payload.attempt > 1 ? <span>第 {item.payload.attempt} 次尝试</span> : null}
        {showStatus ? <ToolStatus status={status} runStatus={runStatus} /> : null}
      </header>

      {Object.keys(item.payload.arguments).length > 0 ? <ToolArguments arguments={item.payload.arguments} /> : null}
      {output?.payload.summary ? (
        <p className="m-0 whitespace-pre-wrap text-[var(--agent-text-secondary)]">{output.payload.summary}</p>
      ) : null}
      {output?.payload.error_message || output?.payload.error_code ? (
        <p className="m-0 text-sm text-[var(--color-danger)]" role="alert">
          {output.payload.error_message || output.payload.error_code}
        </p>
      ) : null}
      {output?.payload.artifact_refs.length ? (
        <div className="flex flex-wrap gap-2">
          {output.payload.artifact_refs.map((reference, referenceIndex) => (
            <Button
              key={reference.artifact_id}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onSelectArtifact?.(reference.artifact_id)}
            >
              <FileOutput aria-hidden="true" />
              <span>{reference.label || `查看结果 ${referenceIndex + 1}`}</span>
              <ArrowUpRight aria-hidden="true" />
            </Button>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function ToolArguments({ arguments: values }: { arguments: Record<string, unknown> }) {
  return (
    <dl className="m-0 grid gap-1 text-xs">
      {Object.entries(values).map(([key, value]) => (
        <div key={key} className="grid grid-cols-[minmax(72px,auto)_minmax(0,1fr)] gap-2">
          <dt className="text-[var(--agent-text-muted)]">{key}</dt>
          <dd className="m-0 whitespace-pre-wrap break-words font-[var(--font-family-code)] text-[var(--agent-text-secondary)]">
            {formatArgument(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Icon-only for the common terminal states; words only where action is needed. */
function ToolStatus({
  status,
  runStatus,
}: {
  status: ConversationRunItem["status"];
  runStatus: ConversationRun["status"];
}) {
  const needsWords = status === "failed" || status === "waiting" || status === "cancelled";
  return (
    <span className={cn(
      "inline-flex shrink-0 items-center gap-1 text-xs",
      status === "failed" && "text-[var(--color-danger)]",
      status === "completed" && "text-[var(--color-success)]",
      (status === "pending" || status === "in_progress") && "text-[var(--agent-accent)]",
      needsWords && status !== "failed" && "text-[var(--agent-text-muted)]",
    )}>
      <ToolStatusIcon status={status} />
      {needsWords ? toolStatusLabel(status, runStatus) : null}
    </span>
  );
}

function ToolStatusIcon({ status }: { status: ConversationRunItem["status"] }) {
  if (status === "pending" || status === "in_progress") return <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />;
  if (status === "failed") return <AlertTriangle className="size-3.5" aria-hidden="true" />;
  if (status === "cancelled") return <CircleStop className="size-3.5" aria-hidden="true" />;
  if (status === "waiting") return <Clock3 className="size-3.5" aria-hidden="true" />;
  return <Check className="size-3.5" aria-hidden="true" />;
}

function ToolCategoryIcon({ category }: { category: ToolGroup["category"] }) {
  if (category === "explore") return <Search className="size-4" />;
  if (category === "query") return <TerminalSquare className="size-4" />;
  if (category === "visualize") return <BarChart3 className="size-4" />;
  return <Settings2 className="size-4" />;
}

function groupStatus(statuses: ConversationRunItem["status"][]): ConversationRunItem["status"] {
  if (statuses.some((status) => status === "failed")) return "failed";
  if (statuses.some((status) => status === "in_progress" || status === "pending")) return "in_progress";
  if (statuses.some((status) => status === "waiting")) return "waiting";
  if (statuses.length > 0 && statuses.every((status) => status === "cancelled")) return "cancelled";
  return "completed";
}

function toolStatusLabel(status: ConversationRunItem["status"], runStatus: ConversationRun["status"]): string {
  if (status === "failed") return "失败";
  if (status === "cancelled" && runStatus === "failed") return "因任务失败终止";
  if (status === "cancelled") return "已取消";
  return "等待授权";
}

function toolCategoryLabel(category: ToolGroup["category"]): string {
  if (category === "explore") return "查找信息";
  if (category === "query") return "执行任务";
  if (category === "visualize") return "生成可视化";
  return "流程控制";
}

function formatArgument(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || value === null) return String(value);
  return JSON.stringify(value, null, 2) ?? String(value);
}

function toolElapsed(items: FunctionCallItem[], outputs: FunctionCallOutputItem[]) {
  const starts = items.map((item) => Date.parse(item.created_at)).filter(Number.isFinite);
  const completions = outputs
    .map((output) => output.completed_at ? Date.parse(output.completed_at) : Number.NaN)
    .filter(Number.isFinite);
  const startedAt = starts.length > 0 ? Math.min(...starts) : null;
  const completedMs = startedAt !== null && completions.length > 0
    ? Math.max(0, Math.max(...completions) - startedAt)
    : null;
  return { startedAt, completedMs };
}

function useElapsedLabel(startedAt: number | null, completedMs: number | null, live: boolean) {
  const maximumLiveElapsedMs = 24 * 60 * 60 * 1_000;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live || startedAt === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [live, startedAt]);
  const duration = completedMs ?? (live && startedAt !== null ? Math.max(0, now - startedAt) : null);
  if (duration === null || duration < 1_000 || (live && duration > maximumLiveElapsedMs)) return "";
  const seconds = Math.floor(duration / 1_000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder === 0 ? `${minutes}m` : `${minutes}m ${remainder}s`;
}
