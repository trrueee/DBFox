import {
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  Check,
  ChevronRight,
  Circle,
  CircleStop,
  Database,
  FileOutput,
  ListChecks,
  Loader2,
  Search,
  Settings2,
  X,
} from "lucide-react";
import type {
  AssistantMessageItem,
  ConversationArtifact,
  ConversationRun,
  ConversationRunItem,
  FunctionCallItem,
  FunctionCallOutputItem,
  PlanItem,
  UserMessageItem,
} from "../../../types/conversation";
import { getUserErrorMessage } from "../../../lib/api/client";
import { completionLimitationLabel } from "../../../lib/presentation";
import { MarkdownContent } from "../../workspace/queryResult/MarkdownContent";
import { ApprovalAuditCard } from "./ApprovalCard";
import {
  isPrimaryConversationArtifact,
  isSqlBackedResultViewArtifact,
} from "./conversationArtifactModels";
import { DataReferencePanel } from "./DataReferencePanel";
import { QuestionCard } from "./QuestionCard";

interface AgentTimelineProps {
  run: ConversationRun;
  items: ConversationRunItem[];
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
  onSelectArtifact?: (artifactId: string) => void;
  resolvingQuestionId?: string | null;
  questionError?: string | null;
  onResolveQuestion?: (
    runId: string,
    questionId: string,
    response: { selected_value?: string; text?: string },
  ) => Promise<void> | void;
}

export function AgentTimeline({
  run,
  items,
  artifacts,
  onOpenSqlConsole,
  onSelectArtifact,
  resolvingQuestionId,
  questionError,
  onResolveQuestion,
}: AgentTimelineProps) {
  const outputs = new Map(
    items
      .filter((item): item is FunctionCallOutputItem => item.type === "function_call_output")
      .map((item) => [item.payload.call_id, item]),
  );
  const primaryArtifacts = artifacts.filter(isPrimaryConversationArtifact);
  const preservedResults = primaryArtifacts.filter(
    (artifact) => artifact.status === "completed" && isSqlBackedResultViewArtifact(artifact),
  );
  const evidenceArtifactIds = new Set(
    items
      .filter(
        (item): item is AssistantMessageItem =>
          item.type === "message" && item.payload.role === "assistant",
      )
      .flatMap((item) => item.payload.evidence.map((evidence) => evidence.artifact_id)),
  );
  const evidenceArtifacts = primaryArtifacts.filter((artifact) =>
    evidenceArtifactIds.has(artifact.id),
  );
  const currentItem = activeItem(items);
  const hasFinalAnswer = items.some(
    (item) => item.type === "message"
      && item.payload.role === "assistant"
      && item.payload.completion_disposition != null
      && item.status !== "cancelled",
  );

  return (
    <section className="conv-agent-timeline" aria-label="Agent 时间线">
      {items.map((item) => {
        if (item.type === "function_call_output") return null;
        if (item.type === "message") {
          if (item.payload.role === "user") {
            return <UserMessage key={item.id} item={item as UserMessageItem} />;
          }
          return (
            <AssistantMessage
              key={item.id}
              item={item as AssistantMessageItem}
              onSelectArtifact={onSelectArtifact}
            />
          );
        }
        if (item.type === "function_call") {
          return (
            <FunctionCall
              key={item.id}
              item={item}
              output={outputs.get(item.payload.call_id)}
              runStatus={run.status}
              onSelectArtifact={onSelectArtifact}
            />
          );
        }
        if (item.type === "plan") return <Plan key={item.id} item={item} />;
        if (item.type === "approval") {
          return (
            <ApprovalAuditCard
              key={item.id}
              approval={item}
              onOpenSqlConsole={onOpenSqlConsole}
            />
          );
        }
        if (item.type === "question") {
          return (
            <QuestionCard
              key={item.id}
              question={item}
              submitting={resolvingQuestionId === item.id}
              error={questionError}
              onRespond={(response) =>
                onResolveQuestion?.(run.id, item.id, response) ?? Promise.resolve()}
            />
          );
        }
        return null;
      })}

      {run.error && (
        <div className="conv-error-card" role="alert">
          {preservedResults.length > 0 ? (
            <>
              <strong>
                分析未完成，但已保留 {preservedResults.length} 个查询结果，可在工件区查看。
              </strong>
              <span>{getUserErrorMessage(run.error.message, "本次分析未完成，请重试。")}</span>
            </>
          ) : (
            getUserErrorMessage(run.error.message, "本次分析未完成，请重试。")
          )}
        </div>
      )}
      {run.status === "cancelled" && (
        <div className="conv-run-cancelled" role="status">
          <CircleStop size={15} aria-hidden="true" />
          <span>任务已停止</span>
        </div>
      )}
      {["created", "queued", "running"].includes(run.status) && !currentItem && (
        <div className="conv-agent-working" role="status" aria-live="polite">
          <span className="conv-agent-working-dot" aria-hidden="true" />
          <span className="conv-agent-working-copy">
            <strong>{items.length === 1 ? "正在理解问题" : "正在组织下一步分析"}</strong>
            <span>根据已有证据决定继续调用工具或给出结论</span>
          </span>
        </div>
      )}
      {hasFinalAnswer && evidenceArtifacts.length > 0 && (
        <DataReferencePanel
          artifacts={evidenceArtifacts}
          onSelectArtifact={onSelectArtifact}
        />
      )}
      {evidenceArtifacts.length === 0 && preservedResults.length > 0 && (
        <DataReferencePanel
          artifacts={preservedResults}
          kind="saved"
          onSelectArtifact={onSelectArtifact}
        />
      )}
    </section>
  );
}

function UserMessage({ item }: { item: UserMessageItem }) {
  return (
    <article className="conv-message conv-message-user">
      <div className="conv-message-body"><p>{item.payload.content}</p></div>
    </article>
  );
}

function AssistantMessage({
  item,
  onSelectArtifact,
}: {
  item: AssistantMessageItem;
  onSelectArtifact?: (artifactId: string) => void;
}) {
  if (item.status === "cancelled" || !item.payload.content) return null;
  const finalAnswer = item.payload.completion_disposition != null;
  return (
    <article
      className="conv-agent-message conv-answer-document"
      data-streaming-reveal={item.status === "in_progress" ? "true" : undefined}
      aria-live={item.status === "in_progress" ? "polite" : undefined}
    >
      {finalAnswer && item.payload.completion_disposition === "bounded_partial" && (
        <div className="conv-completion-limitation" role="status">
          <AlertTriangle size={15} aria-hidden="true" />
          <div>
            <strong>已完成当前可验证的分析</strong>
            <span>{item.payload.limitation_codes.map(completionLimitationLabel).join("；")}</span>
          </div>
        </div>
      )}
      <MarkdownContent
        content={item.payload.content}
        citations={item.payload.evidence}
        onCitation={onSelectArtifact}
      />
    </article>
  );
}

function FunctionCall({
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
  const detailId = `tool-detail-${item.id}`;
  return (
    <details className={`conv-agent-tool is-${status} is-${item.payload.presentation.category}`}>
      <summary aria-controls={detailId}>
        <span
          className="conv-agent-tool-kind"
          title={toolCategoryLabel(item.payload.presentation.category)}
          aria-hidden="true"
        >
          <ToolCategoryIcon category={item.payload.presentation.category} />
        </span>
        <span className="conv-agent-tool-copy">
          <span className="conv-agent-tool-title">
            <span className={`conv-agent-tool-status is-${status}`}>
              {toolStatusLabel(status, runStatus)}
            </span>
            <span>{item.payload.presentation.title}</span>
          </span>
        </span>
        <ChevronRight className="conv-agent-tool-chevron" size={15} aria-hidden="true" />
      </summary>
      <div id={detailId} className="conv-agent-tool-detail">
        <div className="conv-agent-tool-call">
          <span>调用</span>
          <code>{item.payload.name}</code>
          {item.payload.attempt > 1 && <span>第 {item.payload.attempt} 次尝试</span>}
        </div>
        {Object.keys(item.payload.arguments).length > 0 && (
          <ToolArguments arguments={item.payload.arguments} />
        )}
        {output?.payload.summary && (
          <div className="conv-agent-tool-outcome">
            <strong>结果</strong>
            <p>{output.payload.summary}</p>
          </div>
        )}
        {(output?.payload.error_message || output?.payload.error_code) && (
          <p className="conv-agent-tool-error" role="alert">
            {output.payload.error_message || output.payload.error_code}
          </p>
        )}
        {output?.payload.artifact_refs.length ? (
          <div className="conv-agent-tool-artifacts">
            {output.payload.artifact_refs.map((reference, index) => (
              <button
                key={reference.artifact_id}
                type="button"
                onClick={() => onSelectArtifact?.(reference.artifact_id)}
              >
                <FileOutput size={14} aria-hidden="true" />
                <span>{reference.label || `查看结果 ${index + 1}`}</span>
                <ArrowUpRight size={13} aria-hidden="true" />
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </details>
  );
}

function Plan({ item }: { item: PlanItem }) {
  return (
    <details className={`conv-agent-plan is-${item.status}`}>
      <summary>
        <span className="conv-agent-tool-kind is-plan" aria-hidden="true">
          <ListChecks size={16} />
        </span>
        <span className="conv-agent-plan-copy">
          <span>{item.payload.objective}</span>
          <small>
            {toolStatusLabel(item.status)} · {completedPlanSteps(item)} / {item.payload.steps.length} 个阶段完成
          </small>
        </span>
        <ChevronRight className="conv-agent-plan-chevron" size={15} aria-hidden="true" />
      </summary>
      <ol>
        {item.payload.steps.map((step) => (
          <li key={step.id} className={`is-${step.status}`}>
            <PlanStepIcon status={step.status} />
            <span>
              <span>{step.title}</span>
              {step.note && <small>{step.note}</small>}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

function ToolCategoryIcon({
  category,
}: {
  category: FunctionCallItem["payload"]["presentation"]["category"];
}) {
  if (category === "explore") return <Search size={16} />;
  if (category === "query") return <Database size={16} />;
  if (category === "visualize") return <BarChart3 size={16} />;
  return <Settings2 size={16} />;
}

function ToolArguments({ arguments: values }: { arguments: Record<string, unknown> }) {
  return (
    <dl className="conv-agent-tool-arguments">
      {Object.entries(values).map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{formatArgument(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function PlanStepIcon({ status }: { status: PlanItem["payload"]["steps"][number]["status"] }) {
  if (status === "in_progress") {
    return <Loader2 className="is-spinning" size={14} aria-label="进行中" />;
  }
  if (status === "completed") return <Check size={14} aria-label="已完成" />;
  if (status === "blocked") return <AlertTriangle size={14} aria-label="受阻" />;
  if (status === "skipped") return <X size={14} aria-label="已跳过" />;
  return <Circle size={13} aria-label="待处理" />;
}

function toolStatusLabel(
  status: ConversationRunItem["status"],
  runStatus?: ConversationRun["status"],
): string {
  if (status === "in_progress" || status === "pending") return "运行中";
  if (status === "failed") return "失败";
  if (status === "cancelled" && runStatus === "failed") return "因任务失败终止";
  if (status === "cancelled") return "已取消";
  if (status === "waiting") return "等待授权";
  return "已完成";
}

function toolCategoryLabel(
  category: FunctionCallItem["payload"]["presentation"]["category"],
): string {
  if (category === "explore") return "探索数据";
  if (category === "query") return "分析查询";
  if (category === "visualize") return "生成可视化";
  return "流程控制";
}

function formatArgument(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || value === null) {
    return String(value);
  }
  return JSON.stringify(value, null, 2) ?? String(value);
}

function completedPlanSteps(item: PlanItem): number {
  return item.payload.steps.filter((step) => step.status === "completed").length;
}

function activeItem(items: ConversationRunItem[]): ConversationRunItem | undefined {
  return items.findLast((item) => ["pending", "in_progress", "waiting"].includes(item.status));
}
