import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  CircleAlert,
  Database,
  FileCode2,
  FolderTree,
  Inbox,
  TriangleAlert,
} from "lucide-react";

import { AgentPlan } from "../components/agent-elements/AgentPlan";
import { AgentQuestion } from "../components/agent-elements/AgentQuestion";
import { AgentToolGroup } from "../components/agent-elements/AgentToolGroup";
import { UnifiedComposer } from "../components/agent/UnifiedComposer";
import { CellValuePreview } from "../components/data-grid/CellValuePreview";
import { JsonTree } from "../components/data-grid/json";
import type { JsonValue } from "../components/data-grid/jsonValue";
import { FatalErrorFallback } from "../components/ErrorBoundary";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  ErrorState,
  Progress,
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  ShadcnSkeleton,
  Spinner,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tree,
} from "../components/ui";
import { ApiError } from "../lib/api/client";
import { ArtifactTableGrid } from "../features/workspace/artifacts/table/ArtifactTableGrid";
import { ApprovalAuditCard, ApprovalCard } from "../features/conversation/workspace/ApprovalCard";
import { ConversationStreamNotice } from "../features/conversation/workspace/ConversationStreamNotice";
import { MessageList } from "../features/conversation/workspace/MessageList";
import { RunOutcome } from "../features/conversation/workspace/RunOutcome";
import type {
  ApprovalItem,
  AssistantMessageItem,
  ConversationArtifact,
  ConversationPlanStep,
  ConversationRun,
  FunctionCallItem,
  FunctionCallOutputItem,
  PlanItem,
  QuestionItem,
  UserMessageItem,
} from "../types/conversation";
import { ComparisonCandidate, ComparisonGrid } from "./comparisonPrimitives";
import "../features/workspace/artifacts/table/ArtifactTable.css";
import "../features/conversation/workspace/conversationWorkspace.css";
import "./component-comparison.css";

type ComparisonFamily = "composer" | "agent" | "plan" | "approval" | "question" | "outcome" | "history" | "feedback" | "typography" | "runtime" | "surface" | "data";
type ComparisonLocale = "zh" | "en";
type ComparisonViewport = "480" | "720" | "1280" | "1440";
type ComparisonScale = "100" | "125" | "150" | "200";
type ComparisonContrast = "current" | "high";

const FAMILY_STATES = {
  composer: [["idle", "Idle / Send"], ["running", "Running / Stop"], ["running_draft", "Running / Send draft"], ["cancelling", "Cancelling"], ["disabled", "Disabled"], ["loading", "Loading"], ["error", "Error"], ["long", "Long content"]],
  agent: [["active", "Running"], ["completed", "Completed"], ["failed", "Failed"], ["cancelled", "Cancelled"], ["long", "Long tool list"]],
  plan: [["pending", "Pending"], ["active", "Active"], ["waiting", "Waiting"], ["blocked", "Blocked"], ["skipped", "Skipped"], ["completed", "Completed"], ["partial", "Partial"], ["failed", "Failed"], ["cancelled", "Cancelled"], ["long", "Long content"]],
  approval: [["safe", "Safe"], ["warning", "Warning"], ["danger", "Danger"], ["submitting", "Submitting"], ["approved", "Approved"], ["rejected", "Rejected"], ["expired", "Expired"], ["cancelled", "Cancelled"], ["error", "409 / Error"]],
  question: [["option", "Options"], ["free_text", "Free text"], ["submitting", "Submitting"], ["answered", "Answered"], ["expired", "Expired"], ["cancelled", "Cancelled"], ["error", "409 / Error"]],
  outcome: [["failed_preserved", "Failed + results"], ["failed_empty", "Failed + no results"], ["partial_preserved", "Partial + results"], ["partial_empty", "Partial + no results"], ["cancelled_preserved", "Cancelled + results"]],
  history: [["ready", "Older page available"], ["loading", "Loading"], ["error", "Retry"], ["exhausted", "All loaded"]],
  feedback: [["empty", "Empty"], ["loading", "Loading"], ["error", "Error"], ["fatal", "Fatal boundary"], ["success", "Success"], ["long", "Long content"]],
  typography: [["hierarchy", "Hierarchy"], ["data", "Data"], ["code", "Code"], ["long", "Long content"]],
  runtime: [["starting", "Starting"], ["restarting", "Restarting"], ["ready", "Ready"], ["reconnecting", "Stream reconnecting"], ["cursor_rejected", "Cursor rejected"], ["recovered", "Snapshot recovered"], ["stream_failed", "Stream failed"], ["failed", "Engine failed"], ["stopped", "Stopped"]],
  surface: [["result", "Grid"], ["sql", "Tabs"], ["resizing", "Resizable"], ["tree", "Tree"], ["many_tree", "Tree · 500 nodes"]],
  data: [["json", "JSON"], ["deep_json", "Deep JSON"], ["wide_json", "Wide JSON"], ["long_text", "Long text"], ["image", "Image"], ["image_error", "Image error"]],
} as const;

type ComparisonState = (typeof FAMILY_STATES)[ComparisonFamily][number][0];

const COPY = {
  zh: {
    prompt: "分析近 30 天订单转化率，并找出异常渠道",
    longPrompt: "分析近 30 天订单转化率，比较自然流量、付费流量和联盟渠道，并按影响范围列出异常、证据、限制与下一步建议。",
    placeholder: "描述要完成的工作…",
    objective: "定位近 30 天渠道转化异常，并形成可复核的结论",
  },
  en: {
    prompt: "Analyze conversion over the last 30 days and find anomalous channels",
    longPrompt: "Analyze conversion over the last 30 days, compare organic, paid, and affiliate traffic, then list anomalies, evidence, limitations, and next steps by impact.",
    placeholder: "Describe the work to complete…",
    objective: "Find conversion anomalies from the last 30 days and produce a reviewable conclusion",
  },
} as const;

interface SurfaceTreeNode {
  id: string;
  label: string;
  kind: "connection" | "database" | "table";
  children?: SurfaceTreeNode[];
  count?: number;
}

const SURFACE_TREE: SurfaceTreeNode = {
  id: "root",
  label: "",
  kind: "connection",
  children: [{
    id: "analytics",
    label: "Analytics Warehouse",
    kind: "connection",
    children: [{
      id: "analytics/main",
      label: "main",
      kind: "database",
      children: [
        { id: "analytics/main/orders", label: "public.orders", kind: "table", count: 18 },
        { id: "analytics/main/channels", label: "public.channels", kind: "table", count: 9 },
      ],
    }],
  }],
};

const LARGE_SURFACE_TREE: SurfaceTreeNode = {
  id: "large-root",
  label: "",
  kind: "connection",
  children: [{
    id: "large-analytics",
    label: "Analytics Warehouse",
    kind: "connection",
    children: [{
      id: "large-analytics/main",
      label: "main · 500 tables",
      kind: "database",
      children: Array.from({ length: 500 }, (_, index) => ({
        id: `large-analytics/main/table-${index + 1}`,
        label: `public.table_${String(index + 1).padStart(3, "0")}`,
        kind: "table" as const,
        count: (index % 24) + 1,
      })),
    }],
  }],
};

const PLAN_ARTIFACTS: ConversationArtifact[] = [
  planEvidenceArtifact("plan-evidence-2", "渠道访问与订单结果"),
  planEvidenceArtifact("plan-evidence-4", "异常渠道原始证据"),
];

export function ComponentComparison() {
  const [family, setFamily] = useState<ComparisonFamily>("composer");
  const [locale, setLocale] = useState<ComparisonLocale>("zh");
  const [state, setState] = useState<ComparisonState>("idle");
  const [viewport, setViewport] = useState<ComparisonViewport>("1280");
  const [scale, setScale] = useState<ComparisonScale>("125");
  const [contrast, setContrast] = useState<ComparisonContrast>("current");
  const [editedValue, setEditedValue] = useState<string | null>(null);
  const originalContrast = useRef<string | undefined>(undefined);
  const copy = COPY[locale];
  const fixtureValue = state === "long" ? copy.longPrompt : ["running", "cancelling"].includes(state) ? "" : copy.prompt;
  const value = editedValue ?? fixtureValue;

  useEffect(() => {
    const root = document.documentElement;
    if (originalContrast.current === undefined) originalContrast.current = root.dataset.contrast ?? "";
    if (contrast === "high") root.dataset.contrast = "high";
    else if (originalContrast.current) root.dataset.contrast = originalContrast.current;
    else delete root.dataset.contrast;
    return () => {
      if (originalContrast.current) root.dataset.contrast = originalContrast.current;
      else delete root.dataset.contrast;
    };
  }, [contrast]);

  const plan = useMemo(() => buildPlanFixture(state, copy.objective), [copy.objective, state]);
  const agentTools = useMemo(() => buildAgentToolFixture(state), [state]);
  const busy = ["loading", "active", "waiting", "submitting", "starting", "restarting", "reconnecting", "cursor_rejected"].includes(state);

  return (
    <section className="component-comparison" aria-labelledby="component-comparison-title">
      <header className="component-comparison__header">
        <div>
          <span className="component-comparison__eyebrow">Verified source adoption</span>
          <h1 id="component-comparison-title">真实上游组件验证</h1>
          <p>这里只展示实际采用的上游源码；没有真实实现的类别明确标为待调研。</p>
        </div>
        <div className="component-comparison__decision" role="note">
          <CircleAlert size={16} aria-hidden="true" />
          <span>禁止手写候选仿制</span>
        </div>
      </header>

      <div className="component-comparison__controls" aria-label="比较条件">
        <LabSelect label="组件" value={family} onChange={(next) => {
          const nextFamily = next as ComparisonFamily;
          setFamily(nextFamily);
          setState(FAMILY_STATES[nextFamily][0][0]);
          setEditedValue(null);
        }} options={[["composer", "Composer"], ["agent", "Agent UI"], ["plan", "Plan"], ["approval", "Approval"], ["question", "Question"], ["outcome", "Run Outcome"], ["history", "Conversation History"], ["feedback", "Feedback / Error"], ["data", "Data Preview"], ["typography", "Typography / Color"], ["runtime", "Runtime"], ["surface", "Tree / Grid / Surface"]]} />
        <LabSelect label="语言" value={locale} onChange={(next) => { setLocale(next as ComparisonLocale); setEditedValue(null); }} options={[["zh", "中文"], ["en", "English"]]} />
        <LabSelect label="状态" value={state} onChange={(next) => { setState(next as ComparisonState); setEditedValue(null); }} options={FAMILY_STATES[family]} />
        <LabSelect label="视口" value={viewport} onChange={(next) => setViewport(next as ComparisonViewport)} options={[["480", "480 × 800"], ["720", "720 × 800"], ["1280", "1280 × 800"], ["1440", "1440 × 900"]]} />
        <LabSelect label="缩放" value={scale} onChange={(next) => setScale(next as ComparisonScale)} options={[["100", "100%"], ["125", "125%"], ["150", "150%"], ["200", "200%"]]} />
        <LabSelect label="对比度" value={contrast} onChange={(next) => setContrast(next as ComparisonContrast)} options={[["current", "当前设置"], ["high", "High contrast"]]} />
      </div>

      <div className={`component-comparison__viewport component-comparison__viewport--${viewport} component-comparison__viewport--scale-${scale}`} data-locale={locale} data-state={state} aria-busy={busy || undefined}>
        <div className="component-comparison__stage">
          {family === "composer" ? (
            <ComparisonGrid>
              <ComparisonCandidate title="Adopted production" source="Prompt Kit PromptInput + Vercel AI Elements PromptInputSubmit" decision="ADOPT">
                <UnifiedComposer
                  value={value}
                  onChange={setEditedValue}
                  onSubmit={() => undefined}
                      placeholder={copy.placeholder}
                  ariaLabel="Adopted composer"
                  running={["running", "running_draft", "cancelling"].includes(state)}
                  submitting={state === "loading"}
                  cancelling={state === "cancelling"}
                  disabled={state === "disabled" ? "Disabled fixture" : null}
                  error={state === "error" ? "连接已断开，请重试。" : null}
                  onCancel={() => undefined}
                  deliveryMode="queue"
                  onDeliveryModeChange={() => undefined}
                  compact
                />
              </ComparisonCandidate>
            </ComparisonGrid>
          ) : null}
          {family === "plan" ? (
            <ComparisonGrid>
              <ComparisonCandidate title="Adopted production" source="Agent Elements PlanTool + TodoTool registry source" decision="ADOPT">
                <AgentPlan item={plan} artifacts={PLAN_ARTIFACTS} onSelectArtifact={() => undefined} />
              </ComparisonCandidate>
            </ComparisonGrid>
          ) : null}
          {family === "agent" ? (
            <ComparisonGrid>
              <ComparisonCandidate title="Adopted production" source="Agent Elements ToolGroup + GenericTool registry source" decision="ADOPT">
                <AgentToolGroup
                  group={agentTools.group}
                  outputs={agentTools.outputs}
                  runStatus={agentTools.runStatus}
                  onSelectArtifact={() => undefined}
                />
              </ComparisonCandidate>
            </ComparisonGrid>
          ) : null}
          {family === "approval" ? <ApprovalComparison state={state} /> : null}
          {family === "question" ? <QuestionComparison state={state} /> : null}
          {family === "outcome" ? <OutcomeComparison state={state} /> : null}
          {family === "history" ? <HistoryComparison key={state} state={state} /> : null}
          {family === "feedback" ? <FeedbackComparison state={state} /> : null}
          {family === "typography" ? <TypographyComparison state={state} /> : null}
          {family === "runtime" ? <RuntimeComparison state={state} /> : null}
          {family === "surface" ? <SurfaceComparison state={state} /> : null}
          {family === "data" ? <DataPreviewComparison state={state} /> : null}
        </div>
      </div>
    </section>
  );
}

function LabSelect({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: readonly (readonly [string, string])[];
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger size="sm" aria-label={label}><SelectValue /></SelectTrigger>
        <SelectContent>
          {options.map(([optionValue, optionLabel]) => (
            <SelectItem key={optionValue} value={optionValue}>{optionLabel}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}

function FeedbackComparison({ state }: { state: ComparisonState }) {
  const longCopy = state === "long"
    ? "连接中断前完成的查询结果已安全保留在工作区。请先核对已生成的数据，再决定重试剩余步骤，避免重复执行不必要的请求。"
    : "连接已断开，请检查网络后重试。";
  return (
    <ComparisonGrid>
      <ComparisonCandidate title="Adopted production" source="shadcn/ui Empty + Alert + Spinner + Skeleton · HTML details/summary" decision="ADOPT">
        {state === "fatal" ? (
          <FatalErrorFallback onRetry={() => undefined} />
        ) : state === "empty" ? (
          <Empty className="component-comparison__empty">
            <EmptyHeader>
              <EmptyMedia variant="icon"><Inbox aria-hidden="true" /></EmptyMedia>
              <EmptyTitle>暂无查询结果</EmptyTitle>
              <EmptyDescription>运行只读查询后，结果会显示在这里。</EmptyDescription>
            </EmptyHeader>
            <EmptyContent><Button size="sm">打开 SQL 控制台</Button></EmptyContent>
          </Empty>
        ) : state === "loading" ? (
          <div className="component-comparison__feedback-stack" role="status" aria-label="正在加载结果">
            <Alert role="status"><Spinner role="presentation" aria-hidden="true" aria-label={undefined} /><AlertTitle>正在加载结果</AlertTitle><AlertDescription>正在恢复安全的结果分页视图…</AlertDescription></Alert>
            <ShadcnSkeleton className="h-8 w-full" />
            <ShadcnSkeleton className="h-20 w-full" />
          </div>
        ) : state === "error" || state === "long" ? (
          <ErrorState
            title="结果加载失败"
            description={longCopy}
            error={new ApiError(
              "private provider error",
              503,
              "RESULT_VIEW_UNAVAILABLE",
              [{ status: "failed" }],
              { request_id: "lab-request-42" },
            )}
            onRetry={() => undefined}
          />
        ) : (
          <Alert role="status"><CheckCircle2 aria-hidden="true" /><AlertTitle>结果已保存</AlertTitle><AlertDescription>已保留 3 个可复核结果，可在工作区继续查看。</AlertDescription></Alert>
        )}
      </ComparisonCandidate>
    </ComparisonGrid>
  );
}

function ApprovalComparison({ state }: { state: ComparisonState }) {
  const approval = buildApprovalFixture(state);
  const pending = approval.status === "waiting";
  return (
    <ComparisonGrid>
      <ComparisonCandidate title="Adopted production" source="Vercel AI Elements Confirmation" decision="ADOPT">
        {pending ? (
          <ApprovalCard
            approval={approval}
            submitting={state === "submitting"}
            error={state === "error" ? "请求状态已变化，正在读取最新状态。" : null}
            onResolve={() => undefined}
          />
        ) : (
          <ApprovalAuditCard approval={approval} />
        )}
      </ComparisonCandidate>
    </ComparisonGrid>
  );
}

function QuestionComparison({ state }: { state: ComparisonState }) {
  return (
    <ComparisonGrid>
      <ComparisonCandidate title="Adopted production" source="Agent Elements QuestionTool + Radix RadioGroup" decision="ADOPT">
        <AgentQuestion
          question={buildQuestionFixture(state)}
          submitting={state === "submitting"}
          error={state === "error" ? "回答期限可能已结束，正在读取最新状态。" : null}
          onRespond={() => undefined}
        />
      </ComparisonCandidate>
    </ComparisonGrid>
  );
}

function OutcomeComparison({ state }: { state: ComparisonState }) {
  const partial = state === "partial_preserved" || state === "partial_empty";
  const cancelled = state === "cancelled_preserved";
  const preserved = state === "failed_preserved" || state === "partial_preserved" || cancelled;
  const run: ConversationRun = {
    id: "lab-outcome-run",
    session_id: "lab-session",
    input_id: "lab-input",
    session_sequence: 1,
    user_message_id: "lab-user",
    question: "分析渠道转化异常",
    status: cancelled ? "cancelled" : partial ? "completed" : "failed",
    version: 4,
    cancel_requested: false,
    result: {},
    error: partial || cancelled
      ? null
      : { code: "AGENT_RUNTIME_ERROR", message: "模型服务未能继续，请检查模型设置后继续分析。" },
  };
  const finalAnswer: AssistantMessageItem | undefined = partial ? {
    id: "lab-partial-answer",
    type: "message",
    session_id: "lab-session",
    run_id: run.id,
    turn_id: "lab-turn",
    sequence: 2,
    revision: 1,
    status: "completed",
    created_at: "2026-08-27T08:00:00Z",
    completed_at: "2026-08-27T08:00:10Z",
    payload: {
      role: "assistant",
      phase: "final_answer",
      content: "当前结果只覆盖已验证渠道。",
      evidence: [],
      artifact_refs: [],
      completion_disposition: "bounded_partial",
      limitation_codes: ["TOOL_BUDGET_REACHED", "INSUFFICIENT_EVIDENCE"],
    },
  } : undefined;

  return (
    <ComparisonGrid>
      <ComparisonCandidate title="Adopted production" source="shadcn/ui Alert + Fluent MessageBar behavior" decision="ADOPT">
        <RunOutcome
          run={run}
          finalAnswer={finalAnswer}
          artifacts={preserved ? [outcomeResultArtifact()] : []}
          onSelectArtifact={() => undefined}
        />
      </ComparisonCandidate>
    </ComparisonGrid>
  );
}

function HistoryComparison({ state }: { state: ComparisonState }) {
  const [loaded, setLoaded] = useState(state === "exhausted");
  const startSequence = loaded ? 1 : 41;
  const runs = useMemo(
    () => Array.from(
      { length: 121 - startSequence },
      (_, index) => historyRunFixture(startSequence + index),
    ),
    [startSequence],
  );
  const items = useMemo(
    () => runs.flatMap((run) => historyMessageFixtures(run)),
    [runs],
  );
  const hasOlderHistory = !loaded && state !== "exhausted";

  return (
    <ComparisonGrid>
      <ComparisonCandidate title="Adopted production" source="TanStack Virtual Chat + generated bounded history endpoint" decision="ADOPT">
        <div className="component-comparison__history-stage">
          <MessageList
            runs={runs}
            items={items}
            artifacts={[]}
            hasOlderHistory={hasOlderHistory}
            loadingOlderHistory={state === "loading"}
            olderHistoryLoaded={loaded}
            historyLoadError={state === "error" ? "更早的对话记录载入失败，请重试。" : null}
            onLoadOlderHistory={() => {
              setLoaded(true);
              return Promise.resolve(false);
            }}
          />
        </div>
      </ComparisonCandidate>
    </ComparisonGrid>
  );
}

function historyRunFixture(sequence: number): ConversationRun {
  return {
    id: `lab-history-run-${sequence}`,
    session_id: "lab-history-session",
    input_id: `lab-history-input-${sequence}`,
    session_sequence: sequence,
    user_message_id: `lab-history-user-${sequence}`,
    question: `历史问题 ${sequence}`,
    status: "completed",
    version: 1,
    cancel_requested: false,
    result: {},
    error: null,
  };
}

function historyMessageFixtures(run: ConversationRun): [UserMessageItem, AssistantMessageItem] {
  const sequence = run.session_sequence;
  const createdAt = new Date(Date.UTC(2026, 6, 1) + sequence * 60_000).toISOString();
  return [{
    id: run.user_message_id,
    type: "message",
    session_id: run.session_id,
    run_id: run.id,
    sequence: sequence * 2 - 1,
    revision: 1,
    status: "completed",
    created_at: createdAt,
    completed_at: createdAt,
    payload: {
      role: "user",
      content: `历史问题 ${sequence}`,
      evidence: [],
      artifact_refs: [],
      limitation_codes: [],
    },
  }, {
    id: `lab-history-answer-${sequence}`,
    type: "message",
    session_id: run.session_id,
    run_id: run.id,
    turn_id: `lab-history-turn-${sequence}`,
    sequence: sequence * 2,
    revision: 1,
    status: "completed",
    created_at: createdAt,
    completed_at: createdAt,
    payload: {
      role: "assistant",
      phase: "final_answer",
      content: `历史回答 ${sequence}`,
      evidence: [],
      artifact_refs: [],
      completion_disposition: "complete",
      limitation_codes: [],
    },
  }];
}

function DataPreviewComparison({ state }: { state: ComparisonState }) {
  const value = dataPreviewFixture(state);
  return (
    <ComparisonGrid>
      <ComparisonCandidate title="Adopted production" source="react-json-view-lite + Radix Dialog / HoverCard + shadcn/ui Button" decision="ADOPT">
        <div className="component-comparison__data-preview">
          {state === "json" || state === "deep_json" || state === "wide_json" ? (
            <div className="component-comparison__json-stage">
              <JsonTree data={value} />
            </div>
          ) : null}
          <div className="component-comparison__cell-fixture">
            <span>生产单元格触发器</span>
            <CellValuePreview
              value={value}
              dataType={state === "image" || state === "image_error" ? "text" : state === "long_text" ? "text" : "jsonb"}
              columnName={state === "image" || state === "image_error" ? "thumbnail_url" : state === "long_text" ? "analysis_note" : "payload"}
              onCopyValue={() => undefined}
            />
          </div>
        </div>
      </ComparisonCandidate>
    </ComparisonGrid>
  );
}

function dataPreviewFixture(state: ComparisonState): JsonValue {
  if (state === "image") return "https://httpbin.org/image/png?x-oss-process=image";
  if (state === "image_error") return "https://httpbin.org/json?x-oss-process=image";
  if (state === "long_text") {
    return "查询已完成，但联盟渠道缺少最近七天的归因明细。当前结论只覆盖自然搜索和信息流广告；请补齐权限后重新核对联盟渠道。";
  }
  if (state === "wide_json") {
    return { rows: Array.from({ length: 30 }, (_, index) => ({ id: index + 1, status: "verified" })) };
  }
  if (state === "deep_json") {
    return { result: { channel: { metrics: { conversion: { current: 0.0279, previous: 0.041 } } } } };
  }
  return { channel: "信息流广告", visits: 36104, orders: 1008, verified: true };
}

function TypographyComparison({ state }: { state: ComparisonState }) {
  return (
    <ComparisonGrid>
      <ComparisonCandidate title="Adopted production" source="Fluent 2 webLightTheme / webDarkTheme semantic tokens" decision="ADOPT">
        <div className="component-comparison__type-specimen" data-specimen={state}>
          <span className="component-comparison__type-eyebrow">渠道分析 · 已校验</span>
          <h2>近 30 天转化率概览</h2>
          <p>{state === "long" ? "信息流广告的转化率较上期下降 1.31 个百分点；该结论来自已保存的只读查询结果，并保留了数据范围、执行时间和限制说明。" : "信息流广告转化率下降，需要进一步核对投放变更。"}</p>
          <dl><div><dt>访问</dt><dd>36,104</dd></div><div><dt>订单</dt><dd>1,008</dd></div><div><dt>转化率</dt><dd>2.79%</dd></div></dl>
          <code>SELECT channel, COUNT(*) FROM orders GROUP BY channel;</code>
        </div>
      </ComparisonCandidate>
    </ComparisonGrid>
  );
}

function RuntimeComparison({ state }: { state: ComparisonState }) {
  if (["reconnecting", "cursor_rejected", "recovered", "stream_failed"].includes(state)) {
    return (
      <ComparisonGrid>
        <ComparisonCandidate title="Adopted production" source="shadcn/ui Alert + production SSE runtime state" decision="ADOPT">
          <ConversationStreamNotice
            state={state === "reconnecting"
              ? "reconnecting"
              : state === "cursor_rejected"
                ? "recovering_snapshot"
                : state === "recovered"
                  ? "recovered"
                  : "failed"}
            error={state === "stream_failed" ? "实时流协议无法继续，已停止自动重连。" : null}
            onRefresh={() => undefined}
          />
        </ComparisonCandidate>
      </ComparisonGrid>
    );
  }
  const live = state === "starting" || state === "restarting";
  const title = state === "restarting" ? "正在重新启动引擎" : state === "starting" ? "正在启动引擎" : state === "ready" ? "引擎已就绪" : state === "stopped" ? "引擎已停止" : "引擎启动失败";
  return (
    <ComparisonGrid>
      <ComparisonCandidate title="Adopted production" source="Radix Progress + shadcn/ui Alert / Spinner" decision="ADOPT">
        <div className="component-comparison__runtime" aria-busy={live || undefined}>
          <Alert variant={state === "failed" ? "destructive" : "default"} role={state === "failed" ? "alert" : "status"}>
            {live ? <Spinner role="presentation" aria-hidden="true" aria-label={undefined} /> : state === "failed" ? <TriangleAlert aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
            <AlertTitle>{title}</AlertTitle>
            <AlertDescription>{state === "failed" ? "可重试启动；诊断信息不会公开凭据或运行时令牌。" : live ? "正在检查本地 Sidecar 与协议版本。" : "当前状态来自 Electron Host 的权威投影。"}</AlertDescription>
          </Alert>
          {live ? <Progress aria-label={title} /> : null}
        </div>
      </ComparisonCandidate>
    </ComparisonGrid>
  );
}

function buildApprovalFixture(state: ComparisonState): ApprovalItem {
  const terminal = ["approved", "rejected", "expired", "cancelled"].includes(state);
  const decision = terminal ? state === "approved" ? "approved" : state : null;
  return {
    id: "lab-approval",
    type: "approval",
    session_id: "lab-session",
    run_id: "lab-run",
    turn_id: "lab-turn",
    sequence: 1,
    revision: terminal ? 2 : 1,
    status: state === "expired" ? "expired" : state === "cancelled" ? "cancelled" : terminal ? "completed" : "waiting",
    created_at: "2026-08-27T08:00:00Z",
    completed_at: terminal ? "2026-08-27T08:01:00Z" : null,
    payload: {
      version: terminal ? 2 : 1,
      risk_level: state === "safe" ? "safe" : state === "danger" ? "danger" : "warning",
      reason: "该操作会把分析摘要写入项目目录。",
      requested_action: { name: "workspace.write_file", arguments: { path: "reports/summary.md" } },
      decision,
    },
  };
}

function buildQuestionFixture(state: ComparisonState): QuestionItem {
  const answered = state === "answered";
  return {
    id: "lab-question",
    type: "question",
    session_id: "lab-session",
    run_id: "lab-run",
    turn_id: "lab-turn",
    sequence: 1,
    revision: answered || state === "expired" || state === "cancelled" ? 2 : 1,
    status: answered ? "completed" : state === "expired" ? "expired" : state === "cancelled" ? "cancelled" : "waiting",
    created_at: "2026-08-27T08:00:00Z",
    completed_at: answered ? "2026-08-27T08:01:00Z" : null,
    payload: {
      version: answered ? 2 : 1,
      question: "这份分析采用哪个月份口径？",
      reason: "自然月和财务月会产生不同结果。",
      options: state === "free_text" ? [] : [
        { value: "calendar", label: "自然月", description: "按日历月统计" },
        { value: "fiscal", label: "财务月", description: "按结账周期统计" },
      ],
      allow_free_text: true,
      response: answered ? { selected_value: "fiscal", text: "以结账日为准" } : null,
    },
  };
}

function SurfaceComparison({ state }: { state: ComparisonState }) {
  const manyNodes = state === "many_tree";
  const treeFixture = manyNodes ? LARGE_SURFACE_TREE : SURFACE_TREE;
  return (
    <ComparisonGrid>
      <ComparisonCandidate title="Adopted production" source="Zag Tree View + react-resizable-panels + Radix Tabs + TanStack Table" decision="ADOPT">
        <ResizablePanelGroup key={state} direction="horizontal" className="component-comparison__surface" aria-label="工作区面板预览">
          <ResizablePanel defaultSize={32} minSize={22}>
            <div className="component-comparison__tree-stage">
              <div className="component-comparison__tree-title"><FolderTree aria-hidden="true" />对象树</div>
              <Tree
                rootItem={treeFixture}
                ariaLabel="数据库对象树"
                getItemId={(item) => item.id}
                getItemLabel={(item) => item.label}
                getItemChildren={(item) => item.children}
                defaultExpandedIds={manyNodes
                  ? ["large-analytics", "large-analytics/main"]
                  : ["analytics", "analytics/main"]}
                renderItemIcon={(item) => item.kind === "table"
                  ? <FileCode2 aria-hidden="true" />
                  : <Database aria-hidden="true" />}
                renderItemMeta={(item) => item.count == null ? null : item.count}
              />
            </div>
          </ResizablePanel>
          <ResizableHandle aria-label="调整对象树与结果区宽度" />
          <ResizablePanel defaultSize={68} minSize={40}>
            <Tabs defaultValue={state === "sql" ? "sql" : "result"} className="component-comparison__surface-tabs">
              <TabsList aria-label="工作区标签">
                <TabsTrigger value="result"><Database aria-hidden="true" />查询结果</TabsTrigger>
                <TabsTrigger value="sql"><FileCode2 aria-hidden="true" />SQL</TabsTrigger>
              </TabsList>
              <TabsContent value="result">
                <ArtifactTableGrid
                  columns={["渠道", "访问", "订单", "转化率"]}
                  columnTypes={["text", "integer", "integer", "decimal"]}
                  rows={[["自然搜索", 48230, 2214, 0.0459], ["信息流广告", 36104, 1008, 0.0279], ["联盟渠道", 18720, 562, 0.03]]}
                  sort={{ columnIndex: 3, direction: "desc" }}
                  onSort={() => undefined}
                  onCopyCell={() => undefined}
                  emptyLabel="暂无结果"
                />
              </TabsContent>
              <TabsContent value="sql"><pre className="component-comparison__sql"><code>SELECT channel, visits, orders, conversion_rate{`\n`}FROM channel_conversion{`\n`}ORDER BY conversion_rate DESC;</code></pre></TabsContent>
            </Tabs>
          </ResizablePanel>
        </ResizablePanelGroup>
      </ComparisonCandidate>
    </ComparisonGrid>
  );
}

function buildAgentToolFixture(state: ComparisonState) {
  const long = state === "long";
  const count = long ? 8 : 3;
  const names = ["schema_describe_table", "sql_validate", "sql_execute_readonly"];
  const titles = ["读取订单结构", "校验只读查询", "执行渠道分析"];
  const terminalStatus = state === "failed" ? "failed" : state === "cancelled" ? "cancelled" : state === "active" ? "in_progress" : "completed";
  const runStatus: ConversationRun["status"] = state === "failed"
    ? "failed"
    : state === "cancelled"
      ? "cancelled"
      : state === "active"
        ? "running"
        : "completed";
  const items: FunctionCallItem[] = Array.from({ length: count }, (_, index) => {
    const position = index % names.length;
    const status = index === count - 1 ? terminalStatus : "completed";
    return {
      id: `lab-call-${index + 1}`,
      type: "function_call",
      session_id: "lab-session",
      run_id: "lab-run",
      turn_id: "lab-turn",
      sequence: index + 1,
      revision: 1,
      status,
      created_at: `2026-08-26T08:00:${String(index).padStart(2, "0")}Z`,
      completed_at: status === "completed" ? `2026-08-26T08:00:${String(index + 1).padStart(2, "0")}Z` : null,
      payload: {
        call_id: `lab-tool-${index + 1}`,
        name: names[position],
        tool_version: "1",
        presentation: {
          title: long ? `${titles[position]} · 批次 ${index + 1}` : titles[position],
          category: position === 0 ? "explore" : "query",
          visibility: "details",
          progress: status === "in_progress" ? "indeterminate" : "none",
        },
        arguments: position === 0 ? { table: "orders" } : { scope: "近 30 天", readonly: true },
        attempt: 1,
      },
    };
  });
  const outputs = new Map<string, FunctionCallOutputItem>();
  items.forEach((item, index) => {
    if (item.status === "in_progress") return;
    outputs.set(item.payload.call_id, {
      id: `lab-output-${index + 1}`,
      type: "function_call_output",
      session_id: item.session_id,
      run_id: item.run_id,
      turn_id: item.turn_id,
      sequence: count + index + 1,
      revision: 1,
      status: item.status,
      created_at: item.created_at,
      completed_at: item.completed_at,
      payload: {
        call_id: item.payload.call_id,
        output: item.status === "failed" ? "" : "ok",
        summary: item.status === "failed" ? "" : `${item.payload.presentation.title}已完成。`,
        artifact_refs: index === 2 && item.status === "completed" ? [{ artifact_id: "artifact-channel-analysis", label: "查看渠道分析结果" }] : [],
        error_code: item.status === "failed" ? "TOOL_EXECUTION_FAILED" : null,
        error_message: item.status === "failed" ? "查询执行失败，请检查数据库连接后重试。" : null,
      },
    });
  });
  return {
    group: { id: "lab-agent-tools", title: "分析渠道转化", category: "query" as const, items },
    outputs,
    runStatus,
  };
}

function buildPlanFixture(state: ComparisonState, objective: string): PlanItem {
  const stepCount = state === "long" ? 12 : state === "pending" ? 1 : 5;
  const statuses = planStatuses(state, stepCount);
  const titles = [
    "确认指标口径与分析范围",
    "读取渠道访问和订单结果",
    "比较转化率并定位异常",
    "核对异常渠道的原始证据",
    "整理结论、限制与下一步",
  ];
  const steps: ConversationPlanStep[] = Array.from({ length: stepCount }, (_, index) => {
    const title = titles[index] ?? `复核分组 ${index - titles.length + 1} 的指标变化与证据`;
    return {
    id: `step-${index + 1}`,
    title: state === "long" && index === 2 ? `${title}：同时比较自然流量、付费流量、联盟渠道及跨设备归因变化` : title,
    status: statuses[index],
    evidence_required: index === 1 || index === 3,
    artifact_ids: statuses[index] === "completed" && (index === 1 || index === 3)
      ? [`plan-evidence-${index + 1}`]
      : [],
    note: statuses[index] === "blocked" ? "缺少联盟渠道明细读取权限。" : statuses[index] === "skipped" ? "本次运行结束，未继续执行。" : null,
    };
  });
  return {
    id: "lab-plan",
    type: "plan",
    session_id: "lab-session",
    run_id: "lab-run",
    turn_id: "lab-turn",
    sequence: 1,
    revision: 4,
    status: state === "failed" ? "failed" : state === "cancelled" ? "cancelled" : ["waiting", "blocked"].includes(state) ? "waiting" : state === "pending" ? "pending" : ["skipped", "completed", "partial"].includes(state) ? "completed" : "in_progress",
    created_at: "2026-08-26T08:00:00Z",
    completed_at: ["skipped", "completed", "partial", "failed", "cancelled"].includes(state) ? "2026-08-26T08:00:12Z" : null,
    payload: {
      objective: state === "long"
        ? `${objective}。同时覆盖自然流量、付费流量、联盟渠道、跨设备归因、数据完整性、权限限制和可复核证据，并逐项说明统计口径、时间范围、异常阈值与后续动作。`.repeat(5)
        : objective,
      steps,
      summary: ["partial", "blocked", "failed"].includes(state) ? "已完成数据核对；联盟渠道因权限不足未继续分析。" : null,
    },
  };
}

function planStatuses(state: ComparisonState, count: number): ConversationPlanStep["status"][] {
  const fill = (statuses: ConversationPlanStep["status"][]) => Array.from(
    { length: count },
    (_, index) => statuses[index] ?? "pending",
  );
  switch (state) {
    case "pending": return fill(["pending"]);
    case "waiting": return fill(["completed", "in_progress"]);
    case "blocked": return fill(["completed", "completed", "blocked"]);
    case "skipped": return fill(["completed", "completed", "completed", "skipped", "skipped"]);
    case "completed": return fill(Array.from({ length: count }, () => "completed"));
    case "partial":
    case "failed": return fill(["completed", "completed", "blocked", "skipped", "skipped"]);
    case "cancelled": return fill(["completed", "completed", "skipped", "skipped", "skipped"]);
    default: return fill(["completed", "completed", "in_progress"]);
  }
}

function planEvidenceArtifact(id: string, title: string): ConversationArtifact {
  return {
    id,
    session_id: "lab-session",
    run_id: "lab-run",
    turn_id: "lab-turn",
    version: 1,
    type: "markdown",
    title,
    status: "completed",
    visibility: "supporting",
    payload: { content: `# ${title}` },
    provenance: {},
    relations: [],
  };
}

function outcomeResultArtifact(): ConversationArtifact {
  return {
    id: "lab-preserved-result",
    session_id: "lab-session",
    run_id: "lab-outcome-run",
    turn_id: "lab-turn",
    version: 1,
    type: "result_view",
    title: "渠道转化查询结果",
    status: "completed",
    visibility: "primary",
    payload: {
      sourceSqlArtifactId: "lab-sql",
      queryFingerprint: "lab-fingerprint",
      datasourceGeneration: 1,
      columns: ["channel", "conversion_rate"],
      rowCount: 3,
      returnedRows: 3,
      latencyMs: 18,
      executedAt: "2026-08-27T08:00:08Z",
      truncated: false,
    },
    provenance: {},
    relations: [],
  };
}
