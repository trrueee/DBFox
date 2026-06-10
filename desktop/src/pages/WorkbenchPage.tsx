// Force Vite Hot-Reload to clear stale parser cache
import { lazy, Suspense, useState, useMemo, useEffect, useCallback, useRef } from "react";
import gsap from "gsap";
import {
  Database,
  Table2,
  Terminal,
  ChevronDown,
  ChevronRight,
  Plus,
  X,
  Sparkles,
  Search,
  RefreshCw,
  Code2,
  HardDrive,
  Settings,
  Activity,
  Layers
} from "lucide-react";
import { MenuBar, type MenuDef } from "../components/MenuBar";
import { api, createAgentRunDraft, reduceAgentRuntimeEvent } from "../lib/api";
import type { AgentRunDraftState, AgentRunResponse, AgentRuntimeEvent, AgentSessionRunSummary, AgentWorkspaceContext, DataSource, FollowUpSuggestion, Project, QueryResult, SchemaTable } from "../lib/api";
import { EnvironmentsPage } from "./EnvironmentsPage";
import { BackupsPage } from "./BackupsPage";
import { DataSourcesPage } from "./DataSourcesPage";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { PromptDialog } from "../components/PromptDialog";
import { CommandPalette, type CommandItem } from "../components/CommandPalette";
import { useToast } from "../components/Toast";
import { buildAgentFollowUpContext } from "../features/agent/context";
import { AgentWorkspace } from "../features/agent/AgentWorkspace";
import { AgentCopilotPanel } from "../features/agent/AgentCopilotPanel";
import { buildAgentWorkspaceContext } from "../features/agent/workspaceContext";
import { SemanticSettingsPanel } from "../features/semantic/SemanticSettingsPanel";
import { ApiConfigDialog, useApiConfig } from "../components/ApiConfigDialog";

// Tab structure for the workspace
export interface WorkbenchTab {
  id: string; // e.g. "query_123" or "table:users"
  type: "query" | "table" | "er" | "datasources" | "history" | "diagnostics";
  title: string;
  dirty?: boolean;
  closable?: boolean;
  connectionId?: string;
  databaseName?: string;
  tableName?: string;
  activeSubTab?: "data" | "schema" | "er" | "design";
  sqlDraft?: string;
  resultState?: "idle" | "running" | "success" | "error" | "timeout" | "cancelled";
  lastQueryResultPreview?: QueryResult | null;
  lastError?: string | null;
  lastExecutedAt?: number;
  actionTrigger?: {
    type: "execute" | "stop" | "validate" | "export" | "format";
    nonce: number;
  };
}

interface WorkbenchPageProps {
  // Connections and metadata states
  projects: Project[];
  activeProject: Project | null;
  datasources: DataSource[];
  activeDataSource: DataSource | null;
  setActiveDataSource: (ds: DataSource | null) => void;
  schemaTables: SchemaTable[];
  loadingObjects: boolean;
  loadingTree: boolean;
  onRefreshSchemaTables: (datasourceId: string) => Promise<void>;
  onRefreshDatasources: () => Promise<void>;
  onCreateProject: (name: string) => Promise<void>;
}

type QueryTabStatePatch = Pick<WorkbenchTab, "resultState" | "sqlDraft" | "dirty" | "lastQueryResultPreview" | "lastError">;

function compactValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function AgentRunPanel({ result, onOpenSql }: { result: AgentRunResponse; onOpenSql: (sql: string) => void }) {
  const plan = result.query_plan;
  const safety = result.safety || {};
  const execution = result.execution || {};
  const columns = execution.columns || [];
  const rows = execution.rows || [];
  const chart = result.chart_suggestion;
  const badgeVariant = result.success ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive";
  const safetyMessages = Array.isArray(safety.messages) ? safety.messages.map(compactValue) : [];
  const rewriteNotes = Array.isArray(safety.rewrite_notes) ? safety.rewrite_notes.map(compactValue) : [];
  const generationMetadata = safety.generation_metadata as { rewrite?: Record<string, unknown> } | undefined;
  const rewrite = generationMetadata?.rewrite || {};
  const truncatedTables = Array.isArray(rewrite.truncated_tables) ? rewrite.truncated_tables.map(compactValue) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: "0.68rem", lineHeight: 1.45 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm ${badgeVariant}`}>{result.success ? "Agent success" : "Agent stopped"}</span>
        {result.error && <span style={{ color: "var(--accent-red)", textAlign: "right" }}>{result.error}</span>}
      </div>

      <section style={{ padding: 7, background: "var(--bg-secondary)" }}>
        <strong>Question</strong>
        <div style={{ marginTop: 3 }}>{result.question}</div>
      </section>

      <section style={{ padding: 7, background: "var(--bg-secondary)" }}>
        <strong>Query Plan</strong>
        <div style={{ marginTop: 4 }}>Goal: {plan?.analysis_goal || "-"}</div>
        <div>Tables: {plan?.candidate_tables?.join(", ") || "-"}</div>
        <div>Metrics: {(plan?.metrics || []).map(compactValue).join(" | ") || "-"}</div>
        <div>Dimensions: {(plan?.dimensions || []).map(compactValue).join(" | ") || "-"}</div>
        {plan?.risk_notes?.length ? <div style={{ color: "var(--accent-amber)" }}>Risk: {plan.risk_notes.join(" | ")}</div> : null}
      </section>

      <section style={{ padding: 7, background: "var(--bg-secondary)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
          <strong>Candidate SQL</strong>
          {result.sql && (
            <button className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors" onClick={() => onOpenSql(result.sql || "")} style={{ fontSize: "0.64rem" }}>
              Open
            </button>
          )}
        </div>
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.64rem", background: "#fff", padding: 5, marginTop: 4, overflowX: "auto" }}>
          {result.sql || "-"}
        </pre>
      </section>

      <section style={{ padding: 7, background: "var(--bg-secondary)" }}>
        <strong>Safety</strong>
        <div style={{ display: "grid", gridTemplateColumns: "82px 1fr", gap: 3, marginTop: 4 }}>
          <span>Passed</span><span>{compactValue(safety.passed)}</span>
          <span>Can execute</span><span>{compactValue(safety.can_execute)}</span>
          <span>Guardrail</span><span>{compactValue((safety.guardrail as { result?: unknown } | undefined)?.result)}</span>
          <span>Confirm</span><span>{compactValue(safety.requires_confirmation)}</span>
        </div>
        {rewriteNotes.length > 0 && (
          <div style={{ marginTop: 5, color: "var(--text-muted)" }}>
            Rewrite: {rewriteNotes.join(" | ")}
          </div>
        )}
        {rewrite.select_star_column_limit !== undefined && (
          <div style={{ marginTop: 3, color: "var(--accent-amber)" }}>
            SELECT * limit: first {compactValue(rewrite.select_star_column_limit)} columns per table
            {truncatedTables.length > 0 ? ` (${truncatedTables.join(", ")})` : ""}
          </div>
        )}
        {safetyMessages.length > 0 && (
          <div style={{ marginTop: 3, color: "var(--text-muted)" }}>
            Messages: {safetyMessages.join(" | ")}
          </div>
        )}
      </section>

      {columns.length > 0 && rows.length > 0 && (
        <section style={{ padding: 7, background: "var(--bg-secondary)" }}>
          <strong>Execution Result</strong>
          <div style={{ color: "var(--text-muted)", marginTop: 3 }}>
            {execution.rowCount ?? rows.length} rows · {execution.latencyMs ?? 0}ms
          </div>
          <div style={{ overflow: "auto", maxHeight: 180, marginTop: 5, background: "#fff" }}>
            <table className="w-full border-collapse text-xs font-mono tabular-nums">
              <thead>
                <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
              </thead>
              <tbody>
                {rows.slice(0, 20).map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {columns.map((column) => <td key={`${rowIndex}-${column}`}>{compactValue(row[column])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {result.explanation && (
        <section style={{ padding: 7, background: "var(--bg-secondary)" }}>
          <strong>Explanation</strong>
          <pre style={{ whiteSpace: "pre-wrap", margin: "4px 0 0", fontFamily: "var(--font-body)" }}>{result.explanation}</pre>
        </section>
      )}

      {chart && (
        <section style={{ padding: 7, background: "var(--bg-secondary)" }}>
          <strong>Chart Suggestion</strong>
          <div style={{ marginTop: 3 }}>
            {chart.type} · x={chart.x || "-"} · y={chart.y || "-"}
          </div>
          <div style={{ color: "var(--text-muted)" }}>{chart.reason}</div>
        </section>
      )}

      <section style={{ padding: 7, background: "var(--bg-secondary)" }}>
        <strong>Agent Steps</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 5 }}>
          {result.steps.map((step) => (
            <div key={`${step.name}-${step.latency_ms}`} style={{ display: "grid", gridTemplateColumns: "1fr 58px 48px", gap: 4 }}>
              <span>{step.name}</span>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm ${step.status === "failed" ? "bg-destructive/15 text-destructive" : step.status === "skipped" ? "bg-secondary text-secondary-foreground" : "bg-success/15 text-success"}`}>
                {step.status}
              </span>
              <span style={{ textAlign: "right", color: "var(--text-muted)" }}>{step.latency_ms}ms</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

const AGENT_LOADING_STEPS = [
  "正在理解问题",
  "正在匹配可信 schema",
  "正在生成查询计划",
  "正在通过 TrustGate",
  "正在执行并整理证据",
];

const AGENT_STEP_LABELS: Record<string, string> = {
  load_follow_up_context: "Load follow-up context",
  build_schema_context: "Build schema context",
  build_query_plan: "Build query plan",
  generate_sql_candidate: "Generate SQL candidate",
  validate_sql: "Validate SQL",
  revise_sql: "Revise SQL",
  execute_sql: "Execute SQL",
  profile_result: "Profile result",
  suggest_chart: "Suggest chart",
  suggest_followups: "Suggest follow-ups",
  answer_synthesizer: "Synthesize answer",
};

function getRuntimeStepName(event: AgentRuntimeEvent): string | null {
  const name = event.step?.name;
  return typeof name === "string" ? name : null;
}

function getRuntimeLoadingSteps(events?: AgentRuntimeEvent[]) {
  if (!events?.length) {
    return AGENT_LOADING_STEPS.map((label, index) => ({
      label,
      state: index < 2 ? "active" : "queued",
    }));
  }

  const names: string[] = [];
  const states = new Map<string, "active" | "done" | "failed">();
  for (const event of events) {
    const name = getRuntimeStepName(event);
    if (!name || !event.type.startsWith("agent.step.")) continue;
    if (!names.includes(name)) names.push(name);
    if (event.type === "agent.step.started") {
      states.set(name, "active");
    }
    if (event.type === "agent.step.completed") {
      states.set(name, event.step?.status === "failed" ? "failed" : "done");
    }
  }

  return names.map((name) => ({
    label: AGENT_STEP_LABELS[name] || name.replace(/_/g, " "),
    state: states.get(name) || "active",
  }));
}

function AgentLoadingNarrative({ compact = false, prompt, events }: { compact?: boolean; prompt?: string; events?: AgentRuntimeEvent[] }) {
  const runtimeSteps = getRuntimeLoadingSteps(events);
  const artifactCount = events?.filter((event) => event.type === "agent.artifact.created").length ?? 0;
  const failedEvent = events?.find((event) => event.type === "agent.run.failed");

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: compact ? 8 : 12,
        padding: compact ? 8 : 16,
        background: compact ? "var(--bg-secondary)" : "var(--bg-surface)",
        border: compact ? "none" : "1px solid var(--border-light)",
        borderRadius: compact ? 0 : 8,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--accent-indigo)", fontWeight: 800, fontSize: compact ? "0.68rem" : "0.84rem" }}>
        <span className="animate-spin" style={{ fontSize: compact ? 11 : 14 }}>↻</span>
        Agent 正在调查
      </div>
      {prompt?.trim() ? (
        <div style={{ color: "var(--text-secondary)", fontSize: compact ? "0.66rem" : "0.76rem", lineHeight: 1.5 }}>
          {prompt.trim()}
        </div>
      ) : null}
      <div style={{ display: "flex", flexDirection: "column", gap: compact ? 5 : 7 }}>
        {runtimeSteps.map((step) => (
          <div
            key={step.label}
            style={{
              display: "grid",
              gridTemplateColumns: compact ? "16px 1fr" : "22px 1fr",
              alignItems: "center",
              gap: 7,
              color: step.state === "queued" ? "var(--text-secondary)" : "var(--text-primary)",
              fontSize: compact ? "0.66rem" : "0.75rem",
            }}
          >
            <span
              style={{
                width: compact ? 7 : 9,
                height: compact ? 7 : 9,
                borderRadius: "50%",
                background: step.state === "failed" ? "var(--accent-red)" : step.state === "queued" ? "var(--border-medium)" : "var(--accent-indigo)",
                boxShadow: step.state === "active" ? "0 0 0 4px rgba(74,91,192,0.08)" : "none",
                justifySelf: "center",
              }}
            />
            <span>{step.label}</span>
          </div>
        ))}
      </div>
      {artifactCount > 0 || failedEvent ? (
        <div style={{ color: failedEvent ? "var(--accent-red)" : "var(--text-secondary)", fontSize: compact ? "0.64rem" : "0.72rem" }}>
          {failedEvent ? failedEvent.error || "Agent stream failed." : `Artifacts ready: ${artifactCount}`}
        </div>
      ) : null}
    </div>
  );
}

const DashboardPage = lazy(() =>
  import("./DashboardPage").then((module) => ({ default: module.DashboardPage })),
);
const QueryPage = lazy(() =>
  import("./QueryPage").then((module) => ({ default: module.QueryPage })),
);
const SchemaPage = lazy(() =>
  import("./SchemaPage").then((module) => ({ default: module.SchemaPage })),
);
const DataPage = lazy(() =>
  import("./DataPage").then((module) => ({ default: module.DataPage })),
);

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function treeIndent(depth: number) {
  return 4 + depth * 10;
}

function downloadTextFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

const MODULE_PREFIXES: [string, string][] = [
  ["account_", "账号模块"],
  ["ai_", "AI 智能模块"],
  ["agent_", "任务模块"],
  ["auto_", "任务模块"],
  ["billing_", "计费模块"],
  ["content_", "内容模块"],
  ["id_", "身份组织模块"],
  ["login_", "认证会话模块"],
  ["media_", "媒体素材模块"],
  ["monitoring_", "监控模块"],
  ["nurture_", "客户培育模块"],
  ["notification_", "通知模块"],
  ["platform_", "平台账号模块"],
  ["publish_", "发布模块"],
  ["rbac_", "权限模块"],
  ["sales_", "销售模块"],
  ["token_", "Token 账户模块"],
  ["user_", "用户模块"],
  ["video_", "视频模块"],
  ["xhs_", "小红书模块"],
  ["audit_", "审计模块"],
  ["scheduler_", "调度模块"],
];

const MODULE_ORDER = [
  "账号模块",
  "身份组织模块",
  "认证会话模块",
  "平台账号模块",
  "Token 账户模块",
  "销售模块",
  "发布模块",
  "媒体素材模块",
  "视频模块",
  "小红书模块",
  "客户培育模块",
  "AI 智能模块",
  "任务模块",
  "计费模块",
  "审计模块",
  "权限模块",
  "监控模块",
  "通知模块",
  "用户模块",
  "内容模块",
  "调度模块",
  "通用模块",
];

function getModuleTag(tableName: string): string {
  for (const [prefix, tag] of MODULE_PREFIXES) {
    if (tableName.startsWith(prefix)) return tag;
  }
  return "通用模块";
}

function SessionHistoryPanel({
  runs,
  activeRunId,
  replayingRunId,
  onReplay,
}: {
  runs: AgentSessionRunSummary[];
  activeRunId: string | null;
  replayingRunId: string | null;
  onReplay: (runId: string) => void;
}) {
  const STATUS_BADGE: Record<string, { bg: string; color: string; label: string }> = {
    success: { bg: "var(--accent-green)", color: "#fff", label: "Success" },
    failed: { bg: "var(--accent-red)", color: "#fff", label: "Failed" },
    running: { bg: "var(--accent-amber)", color: "#fff", label: "Running" },
    waiting_approval: { bg: "var(--accent-amber)", color: "#fff", label: "Approval" },
  };

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)", marginTop: 8 }}>
      <div style={{ fontSize: "0.64rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 6 }}>
        Session History
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {runs.map((run) => {
          const badge = STATUS_BADGE[run.status] || STATUS_BADGE.failed;
          const isActive = run.run_id === activeRunId;
          const isLoading = run.run_id === replayingRunId;
          return (
            <button
              key={run.run_id}
              onClick={() => onReplay(run.run_id)}
              disabled={isLoading}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
              style={{
                display: "grid",
                gridTemplateColumns: "1fr auto",
                alignItems: "center",
                gap: 6,
                width: "100%",
                padding: "4px 6px",
                border: `1px solid ${isActive ? "var(--accent-indigo)" : "var(--border-light)"}`,
                borderRadius: 4,
                background: isActive ? "rgba(74,91,192,0.06)" : "transparent",
                textAlign: "left",
                cursor: isLoading ? "wait" : "pointer",
                opacity: isLoading ? 0.6 : 1,
                fontSize: "0.66rem",
              }}
            >
              <div style={{ overflow: "hidden" }}>
                <div style={{
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  color: "var(--text-primary)",
                  fontSize: "0.66rem",
                  marginBottom: 2,
                }}>
                  {run.question || "(no question)"}
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--text-muted)", fontSize: "0.6rem" }}>
                  <span>{run.artifact_count ?? 0} artifacts</span>
                  {run.created_at && (
                    <span>{new Date(run.created_at).toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</span>
                  )}
                </div>
              </div>
              <span
                style={{
                  fontSize: "0.58rem",
                  fontWeight: 700,
                  padding: "1px 5px",
                  borderRadius: 3,
                  background: badge.bg,
                  color: badge.color,
                  whiteSpace: "nowrap",
                }}
              >
                {isLoading ? "..." : badge.label}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}


export const WorkbenchPage = ({
  projects,
  activeProject,
  datasources,
  activeDataSource,
  setActiveDataSource,
  schemaTables,
  loadingObjects,
  loadingTree,
  onRefreshSchemaTables,
  onRefreshDatasources,
  onCreateProject,
}: WorkbenchPageProps) => {
  const { toast: showToast } = useToast();
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showBackupsModal, setShowBackupsModal] = useState(false);
  const [showEnvironmentsModal, setShowEnvironmentsModal] = useState(false);
  const [showDashboardModal, setShowDashboardModal] = useState(false);
  const [showCreateProject, setShowCreateProject] = useState(false);

  // Tabs management
  const [tabs, setTabs] = useState<WorkbenchTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  // Object Explorer Tree expansion states
  const [treeSearch, setTreeSearch] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [tablesFolderExpanded, setTablesFolderExpanded] = useState(true);

  // Global resizable AI Panel on the right (defaults to open, resizable, collapsible to 48px strip)
  const [aiPanelCollapsed, setAiPanelCollapsed] = useState(false);
  const apiConfig = useApiConfig();
  const [aiPanelWidth] = useState(340);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiResponse, setAiResponse] = useState("");
  const [agentResponse, setAgentResponse] = useState<AgentRunResponse | null>(null);
  const [agentDraft, setAgentDraft] = useState<AgentRunDraftState | null>(null);
  const [showSemanticSettings, setShowSemanticSettings] = useState(false);
  const [agentStreamEvents, setAgentStreamEvents] = useState<AgentRuntimeEvent[]>([]);
  const [aiMode, setAiMode] = useState<"sql" | "agent">("agent");
  const [aiLoading, setAiLoading] = useState(false);
  const [replayingRunId, setReplayingRunId] = useState<string | null>(null);
  const [sessionRuns, setSessionRuns] = useState<AgentSessionRunSummary[]>([]);

  // ── Load session runs when agent response changes ──
  useEffect(() => {
    if (!agentResponse?.session_id) return;
    api.listAgentSessionRuns(agentResponse.session_id)
      .then(setSessionRuns)
      .catch(() => setSessionRuns([]));
  }, [agentResponse?.session_id]);

  // ── Replay a historical run ──
  const handleReplayRun = useCallback(async (runId: string) => {
    if (!activeDataSource) return;
    setReplayingRunId(runId);
    setAiMode("agent");
    setAiPanelCollapsed(false);
    try {
      const res = await api.getAgentRun(runId);
      if (res) {
        setAgentResponse(res);
        setAgentDraft(null);
        setAgentStreamEvents([]);
        setAiResponse("");
        setAiLoading(false);
      }
    } catch {
      // Run not found — ignore
    } finally {
      setReplayingRunId(null);
    }
  }, [activeDataSource]);

  // Tree context menu
  const [treeContextMenu, setTreeContextMenu] = useState<{
    tableName: string;
    x: number;
    y: number;
  } | null>(null);

  // Command Palette
  const [showCommandPalette, setShowCommandPalette] = useState(false);


  // ── Recover recent agent run on page refresh ──
  useEffect(() => {
    if (!activeDataSource) return;
    let cancelled = false;
    api.getRecentAgentRun(activeDataSource.id).then((res) => {
      if (!cancelled && res) {
        setAgentResponse(res);
        setAiMode("agent");
        setAiPanelCollapsed(false);
      }
    }).catch(() => {
      // No recent run available — ignore
    });
    return () => { cancelled = true; };
  }, [activeDataSource?.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Active tab context RAG
  const activeTab = useMemo(() => {
    return tabs.find(t => t.id === activeTabId) || null;
  }, [tabs, activeTabId]);

  const contentRef = useRef<HTMLDivElement>(null);

  // Subtle fade in on tab/content switch
  useEffect(() => {
    if (contentRef.current) {
      gsap.fromTo(contentRef.current, { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.2, ease: "power1.out" });
    }
  }, [activeTabId]);

  const selectedSchemaTable = useMemo(() => {
    if (activeTab?.type !== "table" || !activeTab.tableName) return null;
    return schemaTables.find((table) => table.table_name === activeTab.tableName) || activeTab.tableName;
  }, [activeTab, schemaTables]);

  const agentWorkspaceContext = useMemo(() => buildAgentWorkspaceContext({
    currentProject: activeProject,
    currentDatasource: activeDataSource,
    activeSql: activeTab?.type === "query" ? activeTab.sqlDraft || "" : "",
    selectedSql: activeTab?.type === "query" ? activeTab.sqlDraft || "" : "",
    lastQueryResult: activeTab?.type === "query" ? activeTab.lastQueryResultPreview || null : null,
    lastError: activeTab?.type === "query" ? activeTab.lastError || null : null,
    selectedTable: selectedSchemaTable,
    selectedColumns: [],
    selectedArtifact: agentResponse?.artifacts?.[0] || null,
    recentAgentRun: agentResponse,
    openSqlTabs: tabs,
  }), [activeProject, activeDataSource, activeTab, agentResponse, selectedSchemaTable, tabs]);

  const handleActiveQueryStateChange = useCallback((state: QueryTabStatePatch) => {
    if (!activeTabId) return;
    setTabs((prev) =>
      prev.map((tab) => {
        if (tab.id !== activeTabId) return tab;
        const nextResultState = state.resultState ?? tab.resultState;
        const nextSqlDraft = state.sqlDraft ?? tab.sqlDraft;
        const nextDirty = state.dirty ?? tab.dirty;
        const nextLastQueryResultPreview = state.lastQueryResultPreview ?? tab.lastQueryResultPreview;
        const nextLastError = state.lastError ?? tab.lastError;
        if (
          tab.resultState === nextResultState &&
          tab.sqlDraft === nextSqlDraft &&
          tab.dirty === nextDirty &&
          tab.lastQueryResultPreview === nextLastQueryResultPreview &&
          tab.lastError === nextLastError
        ) {
          return tab;
        }
        const terminalResult =
          nextResultState &&
          nextResultState !== tab.resultState &&
          ["success", "error", "timeout", "cancelled"].includes(nextResultState);
        return {
          ...tab,
          resultState: nextResultState,
          sqlDraft: nextSqlDraft,
          dirty: nextDirty,
          lastQueryResultPreview: nextLastQueryResultPreview,
          lastError: nextLastError,
          lastExecutedAt: terminalResult ? Date.now() : tab.lastExecutedAt,
        };
      }),
    );
  }, [activeTabId]);

  // Sync focussed tab with left Explorer
  const handleSelectTab = (tabId: string) => {
    setActiveTabId(tabId);
    const tab = tabs.find(t => t.id === tabId);
    if (tab && tab.connectionId && datasources) {
      const boundDs = datasources.find(d => d.id === tab.connectionId);
      if (boundDs && boundDs.id !== activeDataSource?.id) {
        setActiveDataSource(boundDs);
      }
    }
  };

  // Trigger executing, stopping, validating, etc.
  const triggerActiveTabAction = (actionType: "execute" | "stop" | "validate" | "export" | "format") => {
    if (!activeTabId) return;
    setTabs(prev => prev.map(t => t.id === activeTabId ? {
      ...t,
      actionTrigger: {
        type: actionType,
        nonce: Date.now()
      }
    } : t));
  };

  const getEnvBadgeStyle = () => {
    if (!activeDataSource) return { bg: "rgba(148, 163, 184, 0.1)", color: "var(--text-muted)", label: "OFFLINE" };
    if (activeDataSource.env === "prod") return { bg: "rgba(239, 68, 68, 0.12)", color: "var(--accent-red)", label: "PROD" };
    if (activeDataSource.env === "test") return { bg: "rgba(245, 158, 11, 0.12)", color: "var(--accent-amber)", label: "TEST" };
    return { bg: "rgba(16, 185, 129, 0.12)", color: "var(--accent-green)", label: "DEV" };
  };
  const envBadge = getEnvBadgeStyle();

  const filteredTables = useMemo(() => {
    return schemaTables.filter(
      (t) =>
        t.table_name.toLowerCase().includes(treeSearch.toLowerCase()) ||
        t.table_comment.toLowerCase().includes(treeSearch.toLowerCase()),
    );
  }, [schemaTables, treeSearch]);

  const groupedTables = useMemo(() => {
    const groups = new Map<string, SchemaTable[]>();
    for (const t of filteredTables) {
      const tag = t.module_tag || getModuleTag(t.table_name);
      if (!groups.has(tag)) {
        groups.set(tag, []);
      }
      groups.get(tag)!.push(t);
    }
    return Array.from(groups.entries())
      .sort(([left], [right]) => {
        const leftIndex = MODULE_ORDER.indexOf(left);
        const rightIndex = MODULE_ORDER.indexOf(right);
        const normalizedLeft = leftIndex === -1 ? MODULE_ORDER.length : leftIndex;
        const normalizedRight = rightIndex === -1 ? MODULE_ORDER.length : rightIndex;
        return normalizedLeft - normalizedRight || left.localeCompare(right, "zh-Hans-CN");
      })
      .map(([tag, group]) => ({
        tag,
        tables: [...group].sort((a, b) => a.table_name.localeCompare(b.table_name)),
      }));
  }, [filteredTables]);

  const handleOpenQueryTab = useCallback((sqlDraft?: string, title?: string) => {
    const id = `query:${Date.now()}`;
    const newTab: WorkbenchTab = {
      id,
      type: "query",
      title: title || `查询_${tabs.filter(t => t.type === "query").length + 1}`,
      sqlDraft: sqlDraft || "",
      connectionId: activeDataSource?.id,
      databaseName: activeDataSource?.database_name
    };
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(id);
  }, [activeDataSource?.database_name, activeDataSource?.id, tabs]);

  const handleApplySqlToEditor = useCallback((sql: string) => {
    const trimmed = sql.trim();
    if (!trimmed) return;
    if (activeTab?.type === "query" && activeTabId) {
      setTabs((prev) => prev.map((tab) => (
        tab.id === activeTabId
          ? { ...tab, sqlDraft: trimmed, dirty: true }
          : tab
      )));
      showToast("SQL suggestion applied to the current editor.", "success");
      return;
    }
    handleOpenQueryTab(trimmed, "Agent SQL");
    showToast("SQL suggestion opened in a new editor.", "success");
  }, [activeTab, activeTabId, handleOpenQueryTab, showToast]);

  const handleOpenTableTab = (tableName: string, subTab: "data" | "schema" | "er" | "design" = "data") => {
    const id = `table:${tableName}`;
    const exists = tabs.some(t => t.id === id);
    if (exists) {
      setTabs(prev => prev.map(t => t.id === id ? { ...t, activeSubTab: subTab } : t));
      setActiveTabId(id);
    } else {
      const newTab: WorkbenchTab = {
        id,
        type: "table",
        title: `表: ${tableName}`,
        tableName,
        activeSubTab: subTab,
        connectionId: activeDataSource?.id,
        databaseName: activeDataSource?.database_name
      };
      setTabs(prev => [...prev, newTab]);
      setActiveTabId(id);
    }
  };

  const handleCloseTab = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const tab = tabs.find(t => t.id === id);
    if (tab && tab.dirty) {
      const confirmed = window.confirm(`"${tab.title}" 还有未执行或未保存的修改，确认关闭吗？`);
      if (!confirmed) return;
    }
    const nextTabs = tabs.filter(t => t.id !== id);
    setTabs(nextTabs);
    if (activeTabId === id) {
      setActiveTabId(nextTabs[nextTabs.length - 1]?.id || null);
    }
  };

  const handleCloseOtherTabs = () => {
    if (!activeTabId) return;
    const confirmed = window.confirm("确定关闭其他所有标签页吗？");
    if (!confirmed) return;
    setTabs(tabs.filter(t => t.id === activeTabId));
  };

  const handleCloseTabsToRight = () => {
    if (!activeTabId) return;
    const index = tabs.findIndex(t => t.id === activeTabId);
    if (index === -1) return;
    const confirmed = window.confirm("确定关闭右侧所有标签页吗？");
    if (!confirmed) return;
    setTabs(tabs.slice(0, index + 1));
  };

  const handleSwitchSubTab = (tabId: string, subTab: "data" | "schema" | "er" | "design") => {
    setTabs(prev => prev.map(t => t.id === tabId ? { ...t, activeSubTab: subTab } : t));
  };

  const handleGenerateSelect = (tableName: string) => {
    const sql = `SELECT * FROM \`${tableName}\` LIMIT 100;`;
    handleOpenQueryTab(sql, `查询: ${tableName}`);
  };

  const handleAiContextAction = async (promptText: string) => {
    if (!activeDataSource) return;
    // Phase 1: Old Text-to-SQL AI context action replaced by Agent Copilot.
    // Direct the prompt to the Agent chat panel instead.
    setAiPrompt(promptText);
    setAiPanelCollapsed(false);
    handleRunAgentPrompt(promptText);
  };

  const handleRunAgentPrompt = useCallback(async (
    question: string,
    followUpFrom?: AgentRunResponse | null,
    submittedWorkspaceContext?: AgentWorkspaceContext | null,
  ) => {
    if (!question.trim() || !activeDataSource) return;
    const config: Parameters<typeof api.streamAgentQuery>[2] = {
      optimizeRag: true,
      execute: true,
    };
    const baseWorkspaceContext = submittedWorkspaceContext ?? agentWorkspaceContext;
    const workspaceContext = followUpFrom && baseWorkspaceContext
      ? {
          ...baseWorkspaceContext,
          recent_agent_run_id: followUpFrom.run_id,
          selected_artifact_id: baseWorkspaceContext.selected_artifact_id ?? followUpFrom.artifacts?.[0]?.id ?? null,
        }
      : baseWorkspaceContext;
    if (workspaceContext) {
      config.workspaceContext = workspaceContext;
    }
    if (followUpFrom) {
      config.sessionId = followUpFrom.session_id;
      config.parentRunId = followUpFrom.run_id;
      if (followUpFrom.artifacts && followUpFrom.artifacts.length > 0) {
        config.followUpContext = buildAgentFollowUpContext(followUpFrom);
      }
    }
    setAiMode("agent");
    setAiPanelCollapsed(false);
    setAiLoading(true);
    setAiResponse("");
    setAgentResponse(null);
    setAgentDraft(createAgentRunDraft(question));
    setAgentStreamEvents([]);
    setAiPrompt(question);
    try {
      const res = await api.streamAgentQuery(
        activeDataSource.id,
        question,
        config,
        {
          onEvent: (event) => {
            setAgentStreamEvents((prev) => [...prev, event]);
            setAgentDraft((draft) => reduceAgentRuntimeEvent(draft || createAgentRunDraft(question), event));
          },
        },
      );
      setAgentResponse(res);
      if (res.session_id) {
        api.listAgentSessionRuns(res.session_id).then(setSessionRuns).catch(() => {});
      }
      setAgentDraft((draft) => draft ? {
        ...draft,
        status: res.status === "waiting_approval" ? "waiting_approval" : res.success ? "completed" : "failed",
        response: res,
        answer: res.answer || draft.answer || null,
        approval: res.approval || draft.approval || null,
        checkpoint: res.checkpoint || draft.checkpoint || null,
        artifacts: res.artifacts || draft.artifacts,
        error: res.error || null,
      } : draft);
    } catch (err: unknown) {
      setAgentDraft((draft) => draft ? {
        ...draft,
        status: "failed",
        error: getErrorMessage(err, "Agent request failed"),
      } : draft);
      setAiResponse(`Agent 运行失败: ${getErrorMessage(err, "Agent request failed")}`);
    } finally {
      setAiLoading(false);
    }
  }, [activeDataSource, agentWorkspaceContext]);

  const handleAgentRuntimeEvent = useCallback((event: AgentRuntimeEvent) => {
    const fallbackQuestion = agentResponse?.question || aiPrompt || "Agent resume";
    setAgentStreamEvents((prev) => [...prev, event]);
    setAgentDraft((draft) => reduceAgentRuntimeEvent(draft || createAgentRunDraft(fallbackQuestion), event));
  }, [agentResponse?.question, aiPrompt]);

  const handleAgentResumeComplete = useCallback((res: AgentRunResponse) => {
    setAgentResponse(res);
    setAgentDraft((draft) => draft ? {
      ...draft,
      status: res.status === "waiting_approval" ? "waiting_approval" : res.success ? "completed" : "failed",
      response: res,
      answer: res.answer || draft.answer || null,
      approval: res.approval || draft.approval || null,
      checkpoint: res.checkpoint || draft.checkpoint || null,
      artifacts: res.artifacts || draft.artifacts,
      error: res.error || null,
    } : draft);
    if (res.session_id) {
      api.listAgentSessionRuns(res.session_id).then(setSessionRuns).catch(() => {});
    }
  }, []);

  const handleAgentSuggestion = useCallback(async (suggestion: FollowUpSuggestion, result: AgentRunResponse) => {
    if (suggestion.action_type === "save_golden_sql") {
      // Phase 1: Golden SQL deprecated. Use Agent eval tasks (/agent-eval) for golden test cases.
      showToast("Golden SQL 功能已迁移至 Agent 评测模块", "info");
      return;
    }

    if (suggestion.action_type === "export") {
      const sql = result.sql || "";
      if (!sql) {
        showToast("没有可导出的 SQL", "info");
        return;
      }
      downloadTextFile("databox_agent_sql.sql", `${sql}\n`, "text/sql;charset=utf-8");
      showToast("Agent SQL 已导出", "success");
      return;
    }

    await handleRunAgentPrompt(suggestion.question, result);
  }, [activeDataSource, handleRunAgentPrompt, showToast]);

  const handleAskGeneralAi = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!aiPrompt.trim() || !activeDataSource) return;
    // Phase 1: All AI queries now route through the Agent Copilot.
    await handleRunAgentPrompt(aiPrompt);
  };

  const handleSaveCurrentSql = useCallback((saveAs = false) => {
    const sql = activeTab?.type === "query" ? activeTab.sqlDraft?.trim() ?? "" : "";
    if (!sql) {
      showToast("当前没有可保存的 SQL", "info");
      return;
    }
    const baseName = activeTab?.title?.replace(/[\\/:*?"<>|]+/g, "_") || "databox_query";
    const suffix = saveAs ? `_${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}` : "";
    downloadTextFile(`${baseName}${suffix}.sql`, `${sql}\n`, "text/sql;charset=utf-8");
    showToast("SQL 文件已导出", "success");
  }, [activeTab, showToast]);

  const handleExportConnectionConfig = useCallback(() => {
    const payload = datasources.map((ds) => ({
      name: ds.name,
      db_type: ds.db_type,
      host: ds.host,
      port: ds.port,
      database_name: ds.database_name,
      username: ds.username,
      connection_mode: ds.connection_mode,
      is_read_only: ds.is_read_only,
      env: ds.env,
      ssh_enabled: ds.ssh_enabled,
      ssh_host: ds.ssh_host,
      ssh_port: ds.ssh_port,
      ssh_username: ds.ssh_username,
      ssh_pkey_path: ds.ssh_pkey_path,
      ssl_enabled: ds.ssl_enabled,
      ssl_ca_path: ds.ssl_ca_path,
      ssl_cert_path: ds.ssl_cert_path,
      ssl_key_path: ds.ssl_key_path,
      ssl_verify_identity: ds.ssl_verify_identity,
    }));
    downloadTextFile(
      `databox_connections_${new Date().toISOString().slice(0, 10)}.json`,
      JSON.stringify(payload, null, 2),
      "application/json;charset=utf-8",
    );
    showToast("连接配置已导出，密码不会写入文件", "success");
  }, [datasources, showToast]);

  const handleImportConnectionConfig = useCallback(() => {
    setShowSettingsModal(true);
    showToast("请在连接管理器中添加或导入连接配置", "info");
  }, [showToast]);

  const handleTestActiveConnection = useCallback(async () => {
    if (!activeDataSource) {
      showToast("请先选择一个连接", "info");
      return;
    }
    try {
      const result = await api.checkDatasourceHealth(activeDataSource.id);
      showToast(result.message || "连接测试成功", result.ok ? "success" : "warning");
    } catch (error: unknown) {
      showToast(getErrorMessage(error, "连接测试失败"), "error");
    }
  }, [activeDataSource, showToast]);

  // Drag and drop table node to middle editor
  const handleDragStartNode = (e: React.DragEvent, tableName: string) => {
    e.dataTransfer.setData("text/plain", `SELECT * FROM \`${tableName}\` LIMIT 100;`);
    e.dataTransfer.effectAllowed = "copy";
  };

  // Keyboard shortcut listeners
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "t") {
        e.preventDefault();
        handleOpenQueryTab();
      }
      if (mod && e.shiftKey && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setShowCommandPalette(true);
      } else if (mod && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setShowCommandPalette(true);
      }
      if (e.altKey && e.key.toLowerCase() === "a") {
        e.preventDefault();
        setAiPanelCollapsed(prev => !prev);
      }
      if (mod && e.key.toLowerCase() === "w" && activeTabId) {
        e.preventDefault();
        handleCloseTab(activeTabId);
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handleOpenQueryTab, activeTabId, tabs]);

  // Command palette configuration actions
  const commandItems = useMemo<CommandItem[]>(() => {
    return [
      {
        id: "new-query",
        name: "新建 SQL 控制台",
        category: "编辑器",
        shortcut: "Ctrl + T",
        icon: <Terminal size={13} />,
        action: () => handleOpenQueryTab()
      },
      {
        id: "refresh-metadata",
        name: "刷新元数据结构",
        category: "数据源",
        icon: <RefreshCw size={13} />,
        action: () => {
          if (activeDataSource) void onRefreshSchemaTables(activeDataSource.id);
        }
      },
      {
        id: "open-er",
        name: "打开 ER 关系图",
        category: "视图",
        icon: <Layers size={13} />,
        action: () => {
          if (schemaTables[0]) {
            handleOpenTableTab(schemaTables[0].table_name, "er");
          } else {
            alert("没有可用的数据表生成关系图");
          }
        }
      },
      {
        id: "open-settings",
        name: "打开连接管理器",
        category: "设置",
        icon: <Settings size={13} />,
        action: () => setShowSettingsModal(true)
      },
      {
        id: "open-backups",
        name: "打开备份管理器",
        category: "灾备",
        icon: <Database size={13} />,
        action: () => setShowBackupsModal(true)
      },
      {
        id: "open-dashboard",
        name: "打开性能监控面板",
        category: "监控",
        icon: <Activity size={13} />,
        action: () => setShowDashboardModal(true)
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDataSource, handleOpenQueryTab, onRefreshSchemaTables, schemaTables]);

  // Menu bar definitions
  const menus = useMemo<MenuDef[]>(() => {
    const handleCloseWindow = () => {
      try {
        import("@tauri-apps/api/window").then(({ getCurrentWindow }) => {
          getCurrentWindow().close();
        }).catch(() => {});
      } catch { /* non-Tauri env */ }
    };

    const hasConn = !!activeDataSource;

    return [
      {
        id: "file",
        label: "文件",
        items: [
          { label: "新建 SQL 控制台", shortcut: "Ctrl+T", action: () => handleOpenQueryTab() },
          { label: "保存当前 SQL", shortcut: "Ctrl+S", action: () => handleSaveCurrentSql(false) },
          { label: "另存为 SQL 文件", action: () => handleSaveCurrentSql(true) },
          { separator: true, label: "" },
          { label: "导入连接配置", action: handleImportConnectionConfig },
          { label: "导出连接配置", action: handleExportConnectionConfig },
          { separator: true, label: "" },
          { label: "退出", action: handleCloseWindow },
        ],
      },
      {
        id: "edit",
        label: "编辑",
        items: [
          { label: "撤销", shortcut: "Ctrl+Z", action: () => document.execCommand("undo") },
          { label: "重做", shortcut: "Ctrl+Shift+Z", action: () => document.execCommand("redo") },
          { separator: true, label: "" },
          { label: "剪切", shortcut: "Ctrl+X", action: () => document.execCommand("cut") },
          { label: "复制", shortcut: "Ctrl+C", action: () => document.execCommand("copy") },
          { label: "粘贴", shortcut: "Ctrl+V", action: () => document.execCommand("paste") },
          { separator: true, label: "" },
          { label: "格式化 SQL", action: () => triggerActiveTabAction("format") },
        ],
      },
      {
        id: "select",
        label: "选择",
        items: [
          { label: "全选", shortcut: "Ctrl+A", action: () => document.execCommand("selectAll") },
        ],
      },
      {
        id: "view",
        label: "视图",
        items: [
          { label: "显示 / 隐藏 AI 面板", shortcut: "Alt+A", action: () => setAiPanelCollapsed(prev => !prev) },
          { label: "性能监控面板", action: () => setShowDashboardModal(true) },
          { label: "Docker 环境管理", action: () => setShowEnvironmentsModal(true) },
        ],
      },
      {
        id: "go",
        label: "转到",
        items: [
          { label: "快速打开对象", shortcut: "Ctrl+P", action: () => setShowCommandPalette(true) },
          { label: "新建 SQL 控制台", shortcut: "Ctrl+T", action: () => handleOpenQueryTab() },
        ],
      },
      {
        id: "run",
        label: "运行",
        items: [
          { label: "执行当前 SQL", shortcut: "Ctrl+Enter", action: () => triggerActiveTabAction("execute") },
          { label: "停止执行", action: () => triggerActiveTabAction("stop") },
          { separator: true, label: "" },
          { label: "格式化 SQL", action: () => triggerActiveTabAction("format") },
          { label: "安全检查", action: () => triggerActiveTabAction("validate") },
          { label: "导出当前结果", action: () => triggerActiveTabAction("export") },
        ],
      },
      {
        id: "database",
        label: "数据库",
        items: [
          { label: "新建连接", action: () => setShowSettingsModal(true) },
          { label: "测试连接", action: handleTestActiveConnection },
          { label: "断开连接", disabled: !hasConn, action: () => { if (hasConn) setActiveDataSource(null); } },
          { label: "连接设置", action: () => setShowSettingsModal(true) },
          { separator: true, label: "" },
          { label: "刷新结构", disabled: !hasConn, action: () => { if (activeDataSource) void onRefreshSchemaTables(activeDataSource.id); } },
          { label: "打开 SQL 控制台", shortcut: "Ctrl+T", action: () => handleOpenQueryTab() },
          { label: "打开 ER 图", disabled: !hasConn || schemaTables.length === 0, action: () => { if (schemaTables[0]) handleOpenTableTab(schemaTables[0].table_name, "er"); } },
          { separator: true, label: "" },
          { label: "备份数据库", disabled: !hasConn, action: () => setShowBackupsModal(true) },
          { label: "恢复数据库", disabled: !hasConn, action: () => setShowBackupsModal(true) },
        ],
      },
      {
        id: "ai",
        label: "AI",
        items: [
          { label: "打开 AI 面板", shortcut: "Alt+A", action: () => setAiPanelCollapsed(false) },
          { separator: true, label: "" },
          { label: "生成 SQL", action: () => handleAiContextAction("根据当前数据库上下文生成一条可执行的 SELECT SQL。") },
          { label: "解释当前 SQL", action: () => handleAiContextAction("解释当前 SQL 的查询意图、字段逻辑和潜在风险。") },
          { label: "诊断表结构", action: () => handleAiContextAction("诊断当前数据库结构，指出高价值表、索引和关联线索。") },
        ],
      },
      {
        id: "help",
        label: "帮助",
        items: [
          { label: "快捷键参考", action: () => setShowCommandPalette(true) },
          { label: "性能监控面板", action: () => setShowDashboardModal(true) },
          { label: "Docker 环境管理", action: () => setShowEnvironmentsModal(true) },
          { separator: true, label: "" },
          { label: "关于 DataBox", action: () => alert("DataBox v1.0.0\nAI 驱动的本地数据库工作台") },
        ],
      },
    ];
  }, [activeDataSource, handleExportConnectionConfig, handleImportConnectionConfig, handleOpenQueryTab, handleOpenTableTab, handleAiContextAction, handleSaveCurrentSql, handleTestActiveConnection, onRefreshSchemaTables, triggerActiveTabAction, schemaTables, setAiPanelCollapsed, setShowCommandPalette, setShowSettingsModal, setShowBackupsModal, setShowDashboardModal, setShowEnvironmentsModal, setActiveDataSource]);

  const currentAgentEvents = agentDraft?.events.length ? agentDraft.events : agentStreamEvents;
  const hasLiveAgentDraft = Boolean(
    aiMode === "agent" &&
    agentDraft &&
    !agentResponse &&
    (agentDraft.artifacts.length > 0 || agentDraft.answer || agentDraft.status === "failed" || agentDraft.status === "waiting_approval"),
  );

  return (
    <div
      style={{
        display: "grid",
        gridTemplateRows: "30px 1fr 28px",
        height: "100%",
        width: "100%",
        overflow: "hidden",
        background: "var(--bg-primary)"
      }}
    >
      {/* ── Menu Bar ── */}
      <MenuBar menus={menus} />

      {/* ── Layer 2: Main Three-Column Workspace Viewport (Resizable) ── */}
      <main
        style={{
          display: "grid",
          gridTemplateColumns: `230px 1fr ${aiPanelCollapsed ? "48px" : `${aiPanelWidth}px`}`,
          transition: "grid-template-columns 0.18s ease",
          minHeight: 0,
          overflow: "hidden"
        }}
      >
        {/* Column 1: Object Explorer (Left Sidebar) */}
        <aside
          style={{
            display: "flex",
            flexDirection: "column",
            background: "var(--bg-surface)",
            borderRight: "1px solid var(--border-light)",
            overflow: "hidden",
            height: "100%",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
            {/* Explorer Title bar */}
            <div style={{ padding: "5px 6px", display: "flex", justifyContent: "space-between", alignItems: "center", userSelect: "none" }}>
              <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 4 }}>
                <Code2 size={11} style={{ color: "var(--text-muted)" }} />
                对象资源管理器
              </span>
            </div>

            {/* Tree Nodes scrolling container */}
            <div style={{ flex: 1, overflowY: "auto", padding: "2px 4px 6px", display: "flex", flexDirection: "column", gap: 0 }}>
              {loadingTree ? (
                <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                  <div className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: 18, borderRadius: 4 }} />
                  <div className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: 18, borderRadius: 4 }} />
                </div>
              ) : datasources.length === 0 ? (
                <div style={{ padding: "20px 10px", fontSize: "0.72rem", color: "var(--text-muted)", textAlign: "center" }}>
                  无激活连接，请先在右上角添加设置数据源。
                </div>
              ) : (
                datasources.map((ds) => {
                  const isConnected = activeDataSource?.id === ds.id;
                  return (
                    <div key={ds.id} style={{ display: "flex", flexDirection: "column" }}>
                      <button
                        onClick={() => setActiveDataSource(ds)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          width: "100%",
                          minHeight: 23,
                          padding: `2px 4px 2px ${treeIndent(0)}px`,
                          border: "none",
                          borderRadius: 2,
                          background: isConnected ? "var(--bg-active)" : "transparent",
                          color: isConnected ? "var(--accent-indigo)" : "var(--text-secondary)",
                          cursor: "pointer",
                          textAlign: "left",
                        }}
                      >
                        <ChevronRight
                          size={12}
                          style={{
                            transform: isConnected ? "rotate(90deg)" : "rotate(0deg)",
                            transition: "transform 0.1s",
                            opacity: 0.5
                          }}
                        />
                        <Database size={12} style={{ opacity: isConnected ? 1 : 0.6 }} />
                        <span style={{ fontSize: "0.72rem", fontWeight: isConnected ? 700 : 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {ds.name}
                        </span>
                      </button>

                      {isConnected && (
                        <div style={{ marginTop: 1, display: "flex", flexDirection: "column", gap: 1 }}>
                          <div style={{ minHeight: 22, display: "flex", alignItems: "center", gap: 5, padding: `2px 4px 2px ${treeIndent(1)}px`, color: "var(--text-primary)", fontSize: "0.72rem" }}>
                            <ChevronDown size={11} style={{ opacity: 0.5 }} />
                            <HardDrive size={12} style={{ color: "var(--accent-indigo)" }} />
                            <span style={{ fontWeight: 600 }}>{ds.database_name}</span>
                          </div>

                          {/* Semantic Settings button */}
                          <button
                            onClick={() => setShowSemanticSettings(true)}
                            style={{
                              display: "flex", alignItems: "center", gap: 5,
                              width: "100%", minHeight: 22,
                              padding: `2px 4px 2px ${treeIndent(1)}px`,
                              border: "none", background: "transparent",
                              color: "var(--text-secondary)", fontSize: "0.72rem",
                              cursor: "pointer", textAlign: "left",
                            }}
                          >
                            <Settings size={12} style={{ color: "var(--accent-amber)", opacity: 0.8 }} />
                            <span style={{ fontWeight: 500 }}>Semantic Settings</span>
                          </button>

                          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                            {/* Tables Folder */}
                            <div>
                              <button
                                onClick={() => setTablesFolderExpanded(!tablesFolderExpanded)}
                                style={{
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 5,
                                  width: "100%",
                                  minHeight: 22,
                                  padding: `2px 4px 2px ${treeIndent(1)}px`,
                                  border: "none",
                                  background: "transparent",
                                  color: "var(--text-secondary)",
                                  fontSize: "0.72rem",
                                  cursor: "pointer",
                                  textAlign: "left",
                                }}
                              >
                                {tablesFolderExpanded ? <ChevronDown size={11} style={{ opacity: 0.5 }} /> : <ChevronRight size={11} style={{ opacity: 0.5 }} />}
                                <Table2 size={12} style={{ color: "var(--accent-indigo)", opacity: 0.8 }} />
                                <span style={{ fontWeight: 500 }}>表</span>
                                <span style={{ color: "var(--text-muted)", fontSize: "0.64rem" }}>({schemaTables.length})</span>
                              </button>

                              {tablesFolderExpanded && (
                                <div style={{ display: "flex", flexDirection: "column", gap: 1, marginTop: 2 }}>
                                  {/* Filter input */}
                                  <div style={{ display: "flex", gap: 4, padding: `0 2px 0 ${treeIndent(2)}px`, marginBottom: 4 }}>
                                    <div style={{ position: "relative", flex: 1 }}>
                                      <Search size={9} style={{ position: "absolute", left: 5, top: 6, color: "var(--text-muted)" }} />
                                      <input
                                        className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                                        placeholder="过滤数据表..."
                                        value={treeSearch}
                                        onChange={(e) => setTreeSearch(e.target.value)}
                                        style={{ height: 20, fontSize: "0.68rem", paddingLeft: 16, borderColor: "var(--border-light)" }}
                                      />
                                    </div>
                                    <button
                                      className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
                                      onClick={() => void onRefreshSchemaTables(ds.id)}
                                      disabled={loadingObjects}
                                      style={{ padding: "1px 3px", border: "1px solid var(--border-light)", borderRadius: 3 }}
                                    >
                                      <RefreshCw size={9} className={loadingObjects ? "animate-spin" : ""} />
                                    </button>
                                  </div>

                                  {/* Dynamic Groupings */}
                                  <div style={{ display: "flex", flexDirection: "column", gap: 1, maxHeight: 340, overflowY: "auto" }}>
                                    {groupedTables.map(({ tag, tables }) => {
                                      const isCollapsed = collapsedGroups.has(tag);
                                      return (
                                        <div key={tag} style={{ margin: "1px 0" }}>
                                          <button
                                            onClick={() => {
                                              setCollapsedGroups(prev => {
                                                const next = new Set(prev);
                                                if (next.has(tag)) next.delete(tag);
                                                else next.add(tag);
                                                return next;
                                              });
                                            }}
                                            style={{
                                              display: "flex",
                                              alignItems: "center",
                                              width: "100%",
                                              gap: 4,
                                              minHeight: 22,
                                              padding: `2px 4px 2px ${treeIndent(2)}px`,
                                              border: "none",
                                              background: "transparent",
                                              borderRadius: 2,
                                              fontSize: "0.68rem",
                                              fontWeight: 700,
                                              color: "var(--text-secondary)",
                                              cursor: "pointer",
                                              textAlign: "left"
                                            }}
                                          >
                                            <span style={{ fontSize: "0.5rem", transition: "transform 0.1s", transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)" }}>
                                              ▾
                                            </span>
                                            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{tag}</span>
                                            <span style={{ color: "var(--text-muted)", fontSize: "0.6rem" }}>({tables.length})</span>
                                          </button>

                                          {!isCollapsed && (
                                            <div style={{ display: "flex", flexDirection: "column", gap: 1, marginTop: 1 }}>
                                              {tables.map((table) => {
                                                const isTabActive = activeTab?.type === "table" && activeTab.tableName === table.table_name;
                                                return (
                                                  <div
                                                    key={table.id}
                                                    draggable
                                                    onDragStart={(e) => handleDragStartNode(e, table.table_name)}
                                                    onContextMenu={(e) => {
                                                      e.preventDefault();
                                                      setTreeContextMenu({
                                                        tableName: table.table_name,
                                                        x: e.clientX,
                                                        y: e.clientY
                                                      });
                                                    }}
                                                    style={{
                                                      display: "flex",
                                                      alignItems: "center",
                                                      borderRadius: 2,
                                                      background: isTabActive ? "var(--bg-active)" : "transparent",
                                                    }}
                                                    className="tree-item-row"
                                                  >
                                                    <button
                                                      onClick={() => handleOpenTableTab(table.table_name, "schema")}
                                                      onDoubleClick={() => handleOpenTableTab(table.table_name, "data")}
                                                      style={{
                                                        flex: 1,
                                                        display: "flex",
                                                        alignItems: "center",
                                                        gap: 4,
                                                        minHeight: 22,
                                                        padding: `2px 4px 2px ${treeIndent(3)}px`,
                                                        border: "none",
                                                        background: "transparent",
                                                        color: isTabActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                                                        cursor: "pointer",
                                                        textAlign: "left",
                                                        minWidth: 0
                                                      }}
                                                      title={`${table.table_name} (${table.table_comment || "无备注"})`}
                                                    >
                                                      <Table2 size={12} style={{ flexShrink: 0, opacity: isTabActive ? 1 : 0.4 }} />
                                                      <span style={{ fontSize: "0.72rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                        {table.table_name}
                                                      </span>
                                                    </button>
                                                  </div>
                                                );
                                              })}
                                            </div>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </aside>

        {/* Column 2: Workspace tabs area (Middle area) */}
        <section
          style={{
            display: "flex",
            flexDirection: "column",
            height: "100%",
            width: "100%",
            overflow: "hidden",
            borderRight: "1px solid var(--border-light)"
          }}
        >
          {/* Workspace Tabs strip */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              background: "var(--bg-secondary)",
              padding: "4px 8px 0",
              overflowX: "auto",
              flexShrink: 0,
              height: 32,
              userSelect: "none"
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 3, overflowX: "auto", height: "100%" }}>
              {tabs.map((tab) => {
                const isActive = tab.id === activeTabId;
                return (
                  <div
                    key={tab.id}
                    onClick={() => handleSelectTab(tab.id)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      if (window.confirm("确定关闭该标签页吗？")) {
                        handleCloseTab(tab.id);
                      }
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "0 8px",
                      borderRadius: "4px 4px 0 0",
                      background: isActive ? "var(--bg-surface)" : "transparent",
                      border: "1px solid",
                      borderColor: isActive ? "var(--border-light)" : "transparent",
                      borderBottomColor: isActive ? "var(--bg-surface)" : "transparent",
                      color: isActive ? "var(--accent-indigo)" : "var(--text-secondary)",
                      cursor: "pointer",
                      fontSize: "0.72rem",
                      fontWeight: isActive ? 700 : 500,
                      minWidth: "fit-content",
                      height: "100%"
                    }}
                  >
                    {tab.resultState === "running" ? (
                      <span className="animate-spin" style={{ fontSize: "0.68rem" }}>↻</span>
                    ) : tab.type === "query" ? (
                      <Terminal size={10} style={{ opacity: isActive ? 1 : 0.6 }} />
                    ) : (
                      <Table2 size={10} style={{ opacity: isActive ? 1 : 0.6 }} />
                    )}

                    <span>{tab.title}</span>

                    {tab.dirty && (
                      <span style={{ color: "var(--accent-amber)", fontSize: "0.65rem" }}>●</span>
                    )}

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCloseTab(tab.id);
                      }}
                      className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
                      style={{ padding: 1, borderRadius: "50%", color: "var(--text-muted)" }}
                    >
                      <X size={9} />
                    </button>
                  </div>
                );
              })}

              <button
                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
                onClick={() => handleOpenQueryTab()}
                style={{ padding: "2px 5px", display: "flex", alignItems: "center" }}
                title="新建 SQL 查询 (Ctrl+T)"
              >
                <Plus size={11} />
              </button>
            </div>

            {/* Quick clean tab actions */}
            {tabs.length > 1 && (
              <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4, paddingBottom: 2 }}>
                <button
                  className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
                  onClick={handleCloseOtherTabs}
                  style={{ fontSize: "0.66rem", padding: "1px 4px" }}
                >
                  关闭其他
                </button>
                <button
                  className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
                  onClick={handleCloseTabsToRight}
                  style={{ fontSize: "0.66rem", padding: "1px 4px" }}
                >
                  关闭右侧
                </button>
              </div>
            )}
          </div>

          {/* Active Tab content viewport */}
          <div style={{ flex: 1, overflow: "hidden", minHeight: 0, position: "relative" }}>
            {tabs.length === 0 ? (
              hasLiveAgentDraft || agentResponse ? (
                <div style={{ height: "100%", overflow: "auto", padding: 18, background: "var(--bg-primary)" }}>
                  <AgentWorkspace
                    result={agentResponse}
                    draft={agentDraft}
                    disabled={aiLoading}
                    replaying={!agentResponse?.run_id ? false : agentResponse.run_id !== agentDraft?.response?.run_id}
                    workspaceContext={agentWorkspaceContext}
                    onOpenSql={(sql) => handleOpenQueryTab(sql, "Agent SQL")}
                    onApplySql={handleApplySqlToEditor}
                    onAsk={agentResponse ? (question, context) => handleRunAgentPrompt(question, agentResponse, context) : undefined}
                    onSuggestion={handleAgentSuggestion}
                    onRuntimeEvent={handleAgentRuntimeEvent}
                    onResumeComplete={handleAgentResumeComplete}
                  />
                  {sessionRuns.length > 1 && (
                    <SessionHistoryPanel
                      runs={sessionRuns}
                      activeRunId={agentResponse?.run_id || agentDraft?.runId || null}
                      replayingRunId={replayingRunId}
                      onReplay={handleReplayRun}
                    />
                  )}
                </div>
              ) : aiLoading && aiMode === "agent" ? (
                <div style={{ display: "grid", placeItems: "center", height: "100%", padding: 30, background: "var(--bg-primary)" }}>
                  <div style={{ width: "min(620px, 100%)" }}>
                    <AgentLoadingNarrative prompt={aiPrompt} events={currentAgentEvents} />
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", padding: 30, background: "var(--bg-primary)" }}>
                  <div style={{ maxWidth: 620, width: "100%", display: "flex", flexDirection: "column", gap: 14 }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--accent-indigo)", fontWeight: 800, fontSize: "0.82rem", marginBottom: 6 }}>
                        <Sparkles size={15} />
                        Agent 分析入口
                      </div>
                      <div style={{ color: "var(--text-secondary)", fontSize: "0.78rem", lineHeight: 1.6 }}>
                        直接用自然语言描述你要调查的问题，DataBox 会生成 narrative、证据 artifacts、结果表和后续建议。
                      </div>
                    </div>

                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        void handleRunAgentPrompt(aiPrompt);
                      }}
                      style={{ display: "flex", flexDirection: "column", gap: 8 }}
                    >
                      <textarea
                        className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                        placeholder="例如：分析最近 30 天订单趋势，按日期展示订单数和销售额"
                        value={aiPrompt}
                        onChange={(event) => setAiPrompt(event.target.value)}
                        disabled={!activeDataSource || aiLoading}
                        style={{ minHeight: 88, resize: "vertical", fontSize: "0.82rem", lineHeight: 1.55 }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                            event.preventDefault();
                            void handleRunAgentPrompt(aiPrompt);
                          }
                        }}
                      />
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <button
                          type="submit"
                          className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors"
                          disabled={!activeDataSource || aiLoading || !aiPrompt.trim()}
                          style={{ justifyContent: "center", fontSize: "0.78rem", padding: "5px 12px" }}
                        >
                          <Sparkles size={12} />
                          {aiLoading ? "Agent 分析中..." : "运行 Agent 分析"}
                        </button>
                        <button
                          type="button"
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors"
                          onClick={() => handleOpenQueryTab()}
                          style={{ justifyContent: "center", fontSize: "0.78rem", padding: "5px 12px" }}
                        >
                          <Terminal size={12} />
                          高级 SQL 控制台
                        </button>
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
                          onClick={() => setShowCommandPalette(true)}
                          style={{ marginLeft: "auto", fontSize: "0.74rem" }}
                        >
                          命令面板
                        </button>
                      </div>
                    </form>

                    {!activeDataSource && (
                      <div style={{ color: "var(--accent-amber)", fontSize: "0.72rem" }}>
                        请先在左侧选择或创建一个数据源。
                      </div>
                    )}
                  </div>
                </div>
              )
            ) : (
              <div ref={contentRef} style={{ height: "100%", width: "100%" }}>
                {activeTab?.type === "query" && activeDataSource && (
                  <ErrorBoundary title="SQL 终端加载异常">
                    <Suspense fallback={<div className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: "100%" }} />}>
                      <QueryPage
                        key={activeTab.id}
                        datasource={activeDataSource}
                        initialDraft={activeTab.sqlDraft ? { sql: activeTab.sqlDraft, nonce: 1 } : null}
                        actionTrigger={activeTab.actionTrigger}
                        onStateChange={handleActiveQueryStateChange}
                      />
                    </Suspense>
                  </ErrorBoundary>
                )}

                {activeTab?.type === "table" && activeTab.tableName && activeDataSource && (
                  <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%", overflow: "hidden" }}>
                    {/* Context Bar */}
                    <div className="ctx-bar">
                      <span className="ctx-bar-title">{activeTab.tableName}</span>
                      <span className="ctx-bar-meta">
                        {(() => {
                          const t = schemaTables.find(s => s.table_name === activeTab.tableName);
                          if (t) return `${t.columns?.length || 0} columns`;
                          return null;
                        })()}
                      </span>
                      <div className="flex items-center gap-0.5 ml-auto">
                        {(["data", "schema", "er"] as const).map(id => {
                          const labels: Record<string, string> = { data: "Data", schema: "Schema", er: "ER Diagram" };
                          const isActive = (activeTab.activeSubTab || "data") === id;
                          return (
                            <button
                              key={id}
                              onClick={() => handleSwitchSubTab(activeTab.id, id)}
                              className={`ctx-bar-tab ${isActive ? "ctx-bar-tab-active" : "ctx-bar-tab-inactive"}`}
                            >
                              {labels[id]}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    {/* Modular tab pages viewport */}
                    <div style={{ flex: 1, overflow: "hidden", minHeight: 0 }}>
                      {(activeTab.activeSubTab || "data") === "data" && (
                        <ErrorBoundary title="DataTable Preview Error">
                          <Suspense fallback={<div className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: "100%" }} />}>
                            <DataPage
                              datasource={activeDataSource}
                              selectedTableName={activeTab.tableName}
                              schemaTables={schemaTables}
                              onSelectTable={(name) => handleOpenTableTab(name, "data")}
                            />
                          </Suspense>
                        </ErrorBoundary>
                      )}

                      {(activeTab.activeSubTab || "data") === "schema" && (
                        <ErrorBoundary title="Column Definition Schema Error">
                          <Suspense fallback={<div className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: "100%" }} />}>
                            <SchemaPage
                              datasource={activeDataSource}
                              initialViewTab="fields"
                              selectedTableName={activeTab.tableName}
                              onOpenSql={(sql, title) => handleOpenQueryTab(sql, title)}
                            />
                          </Suspense>
                        </ErrorBoundary>
                      )}

                      {(activeTab.activeSubTab || "data") === "er" && (
                        <ErrorBoundary title="ER Graph Diagram Error">
                          <Suspense fallback={<div className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: "100%" }} />}>
                            <SchemaPage
                              datasource={activeDataSource}
                              initialViewTab="er"
                              selectedTableName={activeTab.tableName}
                              onOpenSql={(sql, title) => handleOpenQueryTab(sql, title)}
                            />
                          </Suspense>
                        </ErrorBoundary>
                      )}

                      {(activeTab.activeSubTab || "data") === "design" && (
                        <ErrorBoundary title="AI Table DDL Design Draft Error">
                          <Suspense fallback={<div className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: "100%" }} />}>
                            <SchemaPage
                              datasource={activeDataSource}
                              initialViewTab="design"
                              selectedTableName={activeTab.tableName}
                              onOpenSql={(sql, title) => handleOpenQueryTab(sql, title)}
                            />
                          </Suspense>
                        </ErrorBoundary>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Column 3: Collapsible AI Agent Panel (Right Sidebar) */}
        <aside
          style={{
            display: "flex",
            flexDirection: "column",
            background: "var(--bg-surface)",
            overflow: "hidden",
            height: "100%",
            zIndex: 100
          }}
        >
          <AgentCopilotPanel
            datasource={activeDataSource}
            activeTableName={activeTab?.tableName}
            activeSql={activeTab?.type === "query" ? activeTab.sqlDraft || "" : ""}
            lastQueryResult={activeTab?.type === "query" ? activeTab.lastQueryResultPreview || null : null}
            lastError={activeTab?.type === "query" ? activeTab.lastError || null : null}
            isCollapsed={aiPanelCollapsed}
            onCollapse={() => setAiPanelCollapsed(!aiPanelCollapsed)}
            onInsertSql={handleApplySqlToEditor}
            onRunSql={(sql) => handleOpenQueryTab(sql, "Agent SQL")}
            onOpenQueryTab={handleOpenQueryTab}
            onOpenApiConfig={() => apiConfig.setOpen(true)}
            apiConfigured={apiConfig.isConfigured}
          />
        </aside>

        <ApiConfigDialog
          open={apiConfig.open}
          onOpenChange={apiConfig.setOpen}
          config={apiConfig.config}
          onChange={apiConfig.updateConfig}
          onSave={apiConfig.handleSave}
          saved={apiConfig.saved}
        />
      </main>

      {/* ── Bottom Status Bar ── */}
      <footer
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "var(--bg-secondary)",
          borderTop: "1px solid var(--border-light)",
          padding: "0 12px",
          height: 28,
          fontSize: "0.76rem",
          color: "var(--text-secondary)",
          userSelect: "none"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ color: "var(--accent-green)", fontWeight: 700 }}>
            ● ONLINE
          </span>
          {activeProject && (
            <>
              <span style={{ opacity: 0.4 }}>|</span>
              <span
                onClick={() => setShowCreateProject(true)}
                style={{
                  cursor: "pointer",
                  fontWeight: 600,
                  color: "var(--text-primary)"
                }}
                title="点击切换项目"
              >
                {activeProject.name}
              </span>
            </>
          )}
          {activeDataSource && (
            <>
              <span style={{ opacity: 0.4 }}>|</span>
              <span
                onClick={() => setShowSettingsModal(true)}
                style={{
                  cursor: "pointer",
                  fontWeight: 600,
                  color: "var(--text-primary)"
                }}
                title="点击管理连接"
              >
                {activeDataSource.name}
              </span>
              <span style={{ opacity: 0.4 }}>|</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.66rem" }}>
                {activeDataSource.db_type || "mysql"}
              </span>
              <span style={{ opacity: 0.4 }}>|</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.66rem", color: "var(--accent-indigo)", fontWeight: 600 }}>
                {activeDataSource.database_name}
              </span>
              <span style={{ opacity: 0.4 }}>|</span>
              <span
                style={{
                  fontSize: "0.64rem",
                  fontWeight: 700,
                  padding: "0 4px",
                  borderRadius: 2,
                  background: envBadge.bg,
                  color: envBadge.color,
                }}
              >
                {envBadge.label}
              </span>
              <span style={{ opacity: 0.4 }}>|</span>
              <span>
                只读: <strong style={{ color: "var(--text-primary)" }}>{activeDataSource.is_read_only ? "是" : "否"}</strong>
              </span>
            </>
          )}
          {activeTab?.resultState === "running" && (
            <>
              <span style={{ opacity: 0.4 }}>|</span>
              <span className="animate-pulse" style={{ color: "var(--accent-indigo)", fontWeight: 700 }}>
                执行中...
              </span>
              <button
                onClick={() => triggerActiveTabAction("stop")}
                style={{
                  background: "var(--accent-red)",
                  color: "#fff",
                  border: "none",
                  borderRadius: 3,
                  padding: "0 4px",
                  fontSize: "0.6rem",
                  cursor: "pointer"
                }}
              >
                取消
              </button>
            </>
          )}
          {activeTab?.resultState === "error" && (
            <>
              <span style={{ opacity: 0.4 }}>|</span>
              <span style={{ color: "var(--accent-red)", fontWeight: 700 }}>SQL 执行报错</span>
            </>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {activeTab?.lastExecutedAt && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.64rem", opacity: 0.7 }}>
              已执行
            </span>
          )}
        </div>
      </footer>

      {/* ── Layer 4: Popups and Overlays Modals ── */}

      {/* Object Explorer Tree Context Menu popup */}
      {treeContextMenu && (
        <>
          <div
            onClick={() => setTreeContextMenu(null)}
            onContextMenu={(e) => { e.preventDefault(); setTreeContextMenu(null); }}
            style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 1999 }}
          />
          <div
            style={{
              position: "fixed",
              top: treeContextMenu.y,
              left: treeContextMenu.x,
              minWidth: 160,
              background: "var(--bg-surface)",
              border: "1px solid var(--border-light)",
              borderRadius: 8,
              boxShadow: "var(--shadow-lg)",
              padding: 6,
              zIndex: 2000,
              textAlign: "left"
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: "4px 8px", fontSize: "0.76rem", color: "var(--text-muted)", borderBottom: "1px solid var(--border-light)", marginBottom: 4, fontWeight: 600 }}>
              数据表: {treeContextMenu.tableName}
            </div>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleOpenTableTab(treeContextMenu.tableName, "data");
                setTreeContextMenu(null);
              }}
            >
              打开数据 (Data Preview)
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleOpenTableTab(treeContextMenu.tableName, "schema");
                setTreeContextMenu(null);
              }}
            >
              打开结构字段 (Columns)
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleOpenTableTab(treeContextMenu.tableName, "er");
                setTreeContextMenu(null);
              }}
            >
              查看 ER 实体关联图
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleOpenQueryTab("", `查询: ${treeContextMenu.tableName}`);
                setTreeContextMenu(null);
              }}
            >
              新建 SQL 查询
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleGenerateSelect(treeContextMenu.tableName);
                setTreeContextMenu(null);
              }}
            >
              生成 SELECT SQL
            </button>
            <div style={{ height: 1, background: "var(--border-light)", margin: "4px 0" }} />
            <button
              className="data-table-menu-item"
              onClick={() => {
                void navigator.clipboard.writeText(treeContextMenu.tableName);
                setTreeContextMenu(null);
                showToast?.("表名已复制");
              }}
            >
              复制表名
            </button>
            <button
              className="data-table-menu-item"
              onClick={() => {
                handleAiContextAction(`用物理字段命名规范，详细解释数据库表 ${treeContextMenu.tableName} 的设计含义，并归纳关联模型。`);
                setTreeContextMenu(null);
              }}
            >
              🪄 AI 解释表结构
            </button>
          </div>
        </>
      )}

      {/* Global Command Palette */}
      <CommandPalette
        open={showCommandPalette}
        onClose={() => setShowCommandPalette(false)}
        commands={commandItems}
      />

      {/* Settings Modal (Datasources Manager) */}
      {showSettingsModal && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)", zIndex: 1000, display: "grid", placeItems: "center" }}>
          <div style={{ background: "var(--bg-surface)", width: "80%", height: "85%", borderRadius: 12, border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 20px 50px rgba(0,0,0,0.15)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "var(--text-primary)" }}>连接管理器（数据源设置）</span>
              <button onClick={() => setShowSettingsModal(false)} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors" style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
              <DataSourcesPage
                onSelectDataSource={(ds) => {
                  setActiveDataSource(ds);
                  setShowSettingsModal(false);
                }}
                activeDataSource={activeDataSource}
                activeProject={activeProject}
                onRefreshDatasources={onRefreshDatasources}
              />
            </div>
          </div>
        </div>
      )}

      {/* Environments Config Modal */}
      {showEnvironmentsModal && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)", zIndex: 1000, display: "grid", placeItems: "center" }}>
          <div style={{ background: "var(--bg-surface)", width: "80%", height: "85%", borderRadius: 12, border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 20px 50px rgba(0,0,0,0.15)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "var(--text-primary)" }}>环境配置</span>
              <button onClick={() => setShowEnvironmentsModal(false)} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors" style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
              <EnvironmentsPage
                activeProject={activeProject}
                onRefreshDatasources={onRefreshDatasources}
                onSelectDataSource={(ds) => {
                  setActiveDataSource(ds);
                  setShowEnvironmentsModal(false);
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Backups Manager Modal */}
      {showBackupsModal && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)", zIndex: 1000, display: "grid", placeItems: "center" }}>
          <div style={{ background: "var(--bg-surface)", width: "80%", height: "85%", borderRadius: 12, border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 20px 50px rgba(0,0,0,0.15)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "var(--text-primary)" }}>备份与恢复管理器</span>
              <button onClick={() => setShowBackupsModal(false)} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors" style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
              <BackupsPage
                activeProject={activeProject}
                datasources={datasources}
                activeDataSource={activeDataSource}
              />
            </div>
          </div>
        </div>
      )}

      {/* Performance Monitoring Modal */}
      {showDashboardModal && activeDataSource && (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)", zIndex: 1000, display: "grid", placeItems: "center" }}>
          <div style={{ background: "var(--bg-surface)", width: "80%", height: "85%", borderRadius: 12, border: "1px solid var(--border-light)", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 20px 50px rgba(0,0,0,0.15)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.82rem", color: "var(--text-primary)" }}>性能监控面板</span>
              <button onClick={() => setShowDashboardModal(false)} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors" style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
              <Suspense fallback={<div className="bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer rounded-sm" style={{ height: 240, borderRadius: 8 }} />}>
                <DashboardPage datasource={activeDataSource} />
              </Suspense>
            </div>
          </div>
        </div>
      )}

      {/* Prompt Dialog for New Project */}
      <PromptDialog
        open={showCreateProject}
        title="创建新项目"
        placeholder="请输入项目名称"
        onConfirm={(name) => {
          setShowCreateProject(false);
          void onCreateProject(name);
        }}
        onCancel={() => setShowCreateProject(false)}
      />

      {/* Semantic Settings Modal */}
      {showSemanticSettings && activeDataSource && activeProject && (
        <SemanticSettingsPanel
          datasource={activeDataSource}
          projectId={activeProject.id}
          onClose={() => setShowSemanticSettings(false)}
        />
      )}

    </div>
  );
};
