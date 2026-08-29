import { useMemo } from "react";
import type {
  AssistantMessageItem,
  ConversationArtifact,
  ConversationRun,
  ConversationRunItem,
  FunctionCallItem,
  FunctionCallOutputItem,
  UserMessageItem,
} from "../../../types/conversation";
import { AgentPlan } from "../../../components/agent-elements/AgentPlan";
import { AgentQuestion } from "../../../components/agent-elements/AgentQuestion";
import { AgentTool, AgentToolGroup } from "../../../components/agent-elements/AgentToolGroup";
import { Message, MessageContent } from "../../../components/ai-elements/message";
import { Alert, AlertDescription, AlertTitle, Spinner } from "../../../components/ui";
import { MarkdownContent } from "../../workspace/queryResult/MarkdownContent";
import { artifactEmbedIds } from "../../workspace/queryResult/remarkDbfoxCitations";
import { ArtifactViewHost } from "../../workspace/artifacts/ArtifactViewHost";
import { toArtifactEnvelope } from "../../workspace/artifacts/artifactEnvelope";
import { ApprovalAuditCard } from "./ApprovalCard";
import {
  isPrimaryConversationArtifact,
} from "./conversationArtifactSelectors";
import { DataReferencePanel } from "./DataReferencePanel";
import { RunOutcome } from "./RunOutcome";

interface AgentTimelineProps {
  run: ConversationRun;
  items: ConversationRunItem[];
  artifacts: ConversationArtifact[];
  ariaLabel?: string;
  onOpenSqlConsole?: (sql?: string) => void;
  onSelectArtifact?: (artifactId: string) => void;
  resolvingQuestionId?: string | null;
  questionError?: unknown;
  onResolveQuestion?: (
    runId: string,
    questionId: string,
    response: { selected_value?: string; text?: string },
  ) => Promise<void> | void;
}

type RenderableTimelineItem =
  | { kind: "single"; item: ConversationRunItem }
  | {
      kind: "function_group";
      id: string;
      title: string;
      category: FunctionCallItem["payload"]["presentation"]["category"];
      items: FunctionCallItem[];
    };

export function AgentTimeline({
  run,
  items,
  artifacts,
  ariaLabel = "Agent 时间线",
  onOpenSqlConsole,
  onSelectArtifact,
  resolvingQuestionId,
  questionError,
  onResolveQuestion,
}: AgentTimelineProps) {
  const outputs = useMemo(() => {
    const map = new Map<string, FunctionCallOutputItem>();
    for (const item of items) {
      if (item.type === "function_call_output") {
        map.set(item.payload.call_id, item);
      }
    }
    return map;
  }, [items]);

  const finalAnswer = items.findLast(
    (item): item is AssistantMessageItem => item.type === "message"
      && item.payload.role === "assistant"
      && item.payload.completion_disposition != null
      && item.status !== "cancelled",
  );
  const embeddedArtifactIds = new Set(
    finalAnswer ? artifactEmbedIds(finalAnswer.payload.content) : [],
  );
  const primaryArtifacts = artifacts.filter(isPrimaryConversationArtifact);
  const capabilityArtifacts = primaryArtifacts.filter((artifact) => (
    artifact.status === "completed"
    && artifact.type.includes(".")
    && !embeddedArtifactIds.has(artifact.id)
  ));
  const preservedArtifacts = primaryArtifacts.filter(
    (artifact) => artifact.status === "completed",
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
  const renderableItems = useMemo(() => groupTimelineItems(items), [items]);
  const workingStatus = runWorkingStatus(run.phase ?? null, items.length);

  return (
    <section className="conv-agent-timeline" aria-label={ariaLabel}>
      {renderableItems.map((entry) => {
        if (entry.kind === "function_group") {
          return (
            <AgentToolGroup
              key={entry.id}
              group={entry}
              outputs={outputs}
              runStatus={run.status}
              onSelectArtifact={onSelectArtifact}
            />
          );
        }
        const item = entry.item;
        if (item.type === "message") {
          if (item.payload.role === "user") {
            return <UserMessage key={item.id} item={item as UserMessageItem} />;
          }
          return (
            <AssistantMessage
              key={item.id}
              item={item as AssistantMessageItem}
              artifacts={artifacts}
              onSelectArtifact={onSelectArtifact}
            />
          );
        }
        if (item.type === "function_call") {
          return (
            <AgentTool
              key={item.id}
              item={item}
              output={outputs.get(item.payload.call_id)}
              runStatus={run.status}
              onSelectArtifact={onSelectArtifact}
            />
          );
        }
        if (item.type === "plan") {
          return (
            <AgentPlan
              key={item.id}
              item={item}
              artifacts={artifacts}
              onSelectArtifact={onSelectArtifact}
            />
          );
        }
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
            <AgentQuestion
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

      <RunOutcome
        run={run}
        finalAnswer={finalAnswer}
        artifacts={artifacts}
        onSelectArtifact={onSelectArtifact}
      />
      {["created", "queued", "running"].includes(run.status) && !currentItem && (
        <Alert className="conv-run-alert" role="status" aria-live="polite">
          <Spinner role="presentation" aria-hidden="true" aria-label={undefined} />
          <AlertTitle>{workingStatus.title}</AlertTitle>
          <AlertDescription>{workingStatus.detail}</AlertDescription>
        </Alert>
      )}
      {finalAnswer && evidenceArtifacts.length > 0 && (
        <DataReferencePanel
          artifacts={evidenceArtifacts}
          onSelectArtifact={onSelectArtifact}
        />
      )}
      {capabilityArtifacts.length > 0 && (
        <div className="conv-agent-capability-artifacts">
          {capabilityArtifacts.map((artifact) => (
            <div key={artifact.id}>
              <ArtifactViewHost
                artifact={toArtifactEnvelope(artifact)}
                surface="inline"
                onToast={() => undefined}
                compact
                resolveArtifact={(artifactId) => {
                  const resolved = artifacts.find((candidate) => candidate.id === artifactId);
                  return resolved ? toArtifactEnvelope(resolved) : null;
                }}
                openArtifact={(value) => onSelectArtifact?.(value.id)}
              />
            </div>
          ))}
        </div>
      )}
      {evidenceArtifacts.length === 0 && preservedArtifacts.length > 0 && (
        <DataReferencePanel
          artifacts={preservedArtifacts}
          kind="saved"
          onSelectArtifact={onSelectArtifact}
        />
      )}
    </section>
  );
}

function runWorkingStatus(
  phase: ConversationRun["phase"],
  itemCount: number,
): { title: string; detail: string } {
  switch (phase) {
    case "streaming_answer":
      return { title: "正在生成回复", detail: "内容会在生成后持续显示" };
    case "preparing_tool_call":
      return { title: "正在准备工具调用", detail: "模型正在生成结构化参数" };
    case "executing_tool":
      return { title: "正在执行工具", detail: "正在等待能力返回可验证结果" };
    case "waiting_approval":
      return { title: "等待确认", detail: "请处理上方的操作确认" };
    case "finalizing":
      return { title: "正在整理结果", detail: "正在生成最终可交付回复" };
    case "waiting_model":
    default:
      return {
        title: itemCount === 1 ? "正在等待模型响应" : "正在准备下一步",
        detail: "模型可能正在生成回答或准备结构化工具调用",
      };
  }
}

function UserMessage({ item }: { item: UserMessageItem }) {
  return (
    <Message from="user" className="conv-message">
      <MessageContent className="conv-message-body"><p>{item.payload.content}</p></MessageContent>
    </Message>
  );
}

function AssistantMessage({
  item,
  artifacts,
  onSelectArtifact,
}: {
  item: AssistantMessageItem;
  artifacts: ConversationArtifact[];
  onSelectArtifact?: (artifactId: string) => void;
}) {
  if (item.status === "cancelled" || !item.payload.content) return null;
  const renderArtifact = (artifactId: string) => {
    const artifact = artifacts.find((candidate) => candidate.id === artifactId);
    if (!artifact) {
      return (
        <Alert className="conv-run-alert" variant="destructive" role="alert">
          <AlertTitle>嵌入工件暂不可用</AlertTitle>
          <AlertDescription>回答保留了工件引用，但当前投影未包含该工件。</AlertDescription>
        </Alert>
      );
    }
    return (
      <ArtifactViewHost
        artifact={toArtifactEnvelope(artifact)}
        surface="inline"
        onToast={() => undefined}
        compact
        resolveArtifact={(candidateId) => {
          const resolved = artifacts.find((candidate) => candidate.id === candidateId);
          return resolved ? toArtifactEnvelope(resolved) : null;
        }}
        openArtifact={(value) => onSelectArtifact?.(value.id)}
      />
    );
  };
  return (
    <Message
      from="assistant"
      className="conv-agent-message"
      data-streaming-reveal={item.status === "in_progress" ? "true" : undefined}
      aria-live={item.status === "in_progress" ? "polite" : undefined}
    >
      <MessageContent className="conv-answer-document">
        <MarkdownContent
          content={item.payload.content}
          citations={item.payload.evidence}
          artifactRefs={item.payload.artifact_refs}
          onCitation={onSelectArtifact}
          renderArtifact={renderArtifact}
        />
      </MessageContent>
    </Message>
  );
}

function activeItem(items: ConversationRunItem[]): ConversationRunItem | undefined {
  return items.findLast((item) => ["pending", "in_progress", "waiting"].includes(item.status));
}

function groupTimelineItems(items: ConversationRunItem[]): RenderableTimelineItem[] {
  const result: RenderableTimelineItem[] = [];
  let currentGroup: FunctionCallItem[] = [];

  const flushGroup = () => {
    if (currentGroup.length === 0) return;
    if (currentGroup.length === 1) {
      result.push({ kind: "single", item: currentGroup[0] });
    } else {
      const first = currentGroup[0];
      result.push({
        kind: "function_group",
        id: `group-${first.id}-${currentGroup.length}`,
        title: first.payload.presentation.title,
        category: first.payload.presentation.category,
        items: [...currentGroup],
      });
    }
    currentGroup = [];
  };

  for (const item of items) {
    if (item.type === "function_call_output") continue;
    if (item.type === "function_call" && item.payload.presentation.visibility !== "developer") {
      const last = currentGroup[currentGroup.length - 1];
      if (!last || last.payload.presentation.title === item.payload.presentation.title) {
        currentGroup.push(item);
        continue;
      }
    }
    flushGroup();
    result.push({ kind: "single", item });
  }
  flushGroup();

  return result;
}
