import { useState } from "react";
import {
  ChevronDown,
  CircleAlert,
  Clock3,
  Database,
  FileCode2,
  Folder,
  GitBranch,
  Home,
  Maximize2,
  MessageSquare,
  Moon,
  PackageOpen,
  PanelRightClose,
  Plus,
  Settings,
  Sun,
  X,
} from "lucide-react";

import { UnifiedComposer } from "../components/agent/UnifiedComposer";
import { AgentQuestion } from "../components/agent-elements/AgentQuestion";
import {
  Sources,
  SourcesContent,
  SourcesTrigger,
} from "../components/ai-elements/sources";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarNavRow,
  Button,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui";
import { AgentTimeline } from "../features/conversation/workspace/AgentTimeline";
import { ApprovalCard } from "../features/conversation/workspace/ApprovalCard";
import { useTheme } from "../hooks/themeContext";
import type {
  ApprovalItem,
  ConversationRun,
  ConversationRunItem,
  QuestionItem,
} from "../types/conversation";
import { ComponentComparison } from "./ComponentComparison";
import "../features/conversation/workspace/conversationWorkspace.css";
import "./design-lab.css";

type LabSection = "compare" | "shell" | "agent" | "surface" | "settings";

const labRun: ConversationRun = {
  id: "lab-run",
  session_id: "lab-session",
  input_id: "lab-input",
  session_sequence: 1,
  user_message_id: "lab-user",
  question: "整理本月项目进展，并标出需要关注的变化。",
  status: "completed",
  version: 8,
  phase: "finalizing",
  cancel_requested: false,
  result: {},
  error: null,
};

const labItems: ConversationRunItem[] = [
  {
    id: "lab-user", type: "message", session_id: "lab-session", run_id: "lab-run",
    sequence: 1, revision: 1, status: "completed", created_at: "2026-08-26T08:00:00Z",
    payload: { role: "user", content: "整理本月项目进展，并标出需要关注的变化。", evidence: [], artifact_refs: [], limitation_codes: [] },
  },
  {
    id: "lab-commentary", type: "message", session_id: "lab-session", run_id: "lab-run",
    sequence: 2, revision: 1, status: "completed", created_at: "2026-08-26T08:00:01Z",
    payload: { role: "assistant", phase: "commentary", content: "我先核对项目口径、近期记录和已有工件。", evidence: [], artifact_refs: [], limitation_codes: [] },
  },
  {
    id: "lab-plan", type: "plan", session_id: "lab-session", run_id: "lab-run",
    sequence: 3, revision: 3, status: "completed", created_at: "2026-08-26T08:00:02Z",
    payload: {
      objective: "形成可验证的项目进展摘要",
      steps: [
        { id: "step-1", title: "汇总项目上下文", status: "completed" },
        { id: "step-2", title: "核对近期工作记录", status: "completed" },
        { id: "step-3", title: "整理结论与证据", status: "completed" },
      ],
      summary: "已完成",
    },
  },
  {
    id: "lab-tool-1", type: "function_call", session_id: "lab-session", run_id: "lab-run",
    sequence: 4, revision: 1, status: "completed", created_at: "2026-08-26T08:00:03Z",
    payload: { call_id: "lab-call-1", name: "workspace.search", tool_version: "1", presentation: { title: "读取项目上下文", category: "explore", visibility: "details", progress: "indeterminate" }, arguments: { scope: "current_project" }, attempt: 1 },
  },
  {
    id: "lab-output-1", type: "function_call_output", session_id: "lab-session", run_id: "lab-run",
    sequence: 5, revision: 1, status: "completed", created_at: "2026-08-26T08:00:04Z",
    payload: { call_id: "lab-call-1", output: "", summary: "已读取项目说明与 4 项上下文贡献", artifact_refs: [] },
  },
  {
    id: "lab-tool-2", type: "function_call", session_id: "lab-session", run_id: "lab-run",
    sequence: 6, revision: 1, status: "completed", created_at: "2026-08-26T08:00:05Z",
    payload: { call_id: "lab-call-2", name: "workspace.search", tool_version: "1", presentation: { title: "读取项目上下文", category: "explore", visibility: "details", progress: "indeterminate" }, arguments: { include_recent: true }, attempt: 1 },
  },
  {
    id: "lab-output-2", type: "function_call_output", session_id: "lab-session", run_id: "lab-run",
    sequence: 7, revision: 1, status: "completed", created_at: "2026-08-26T08:00:06Z",
    payload: { call_id: "lab-call-2", output: "", summary: "已核对 6 条近期工作记录", artifact_refs: [] },
  },
  {
    id: "lab-answer", type: "message", session_id: "lab-session", run_id: "lab-run",
    sequence: 8, revision: 2, status: "completed", created_at: "2026-08-26T08:00:07Z",
    payload: { role: "assistant", phase: "final_answer", content: "本月核心目标整体按计划推进。两个交付项已完成，当前需要重点关注跨团队确认仍未结束；建议把它设为下一次跟进的首要事项。", evidence: [], artifact_refs: [], completion_disposition: "complete", limitation_codes: [] },
  },
];

const streamingRun: ConversationRun = { ...labRun, id: "lab-streaming-run", status: "running", phase: "streaming_answer" };
const streamingItems: ConversationRunItem[] = [
  { ...labItems[0], id: "stream-user", run_id: streamingRun.id },
  {
    id: "stream-answer", type: "message", session_id: "lab-session", run_id: streamingRun.id,
    sequence: 2, revision: 4, status: "in_progress", created_at: "2026-08-26T08:05:00Z",
    payload: { role: "assistant", phase: "final_answer", content: "正在整理已核对的信息，并生成一份可以直接继续工作的摘要…", evidence: [], artifact_refs: [], limitation_codes: [] },
  },
];

const labQuestion: QuestionItem = {
  id: "lab-question", type: "question", session_id: "lab-session", run_id: "lab-run",
  sequence: 9, revision: 1, status: "waiting", created_at: "2026-08-26T08:06:00Z",
  payload: {
    version: 1,
    question: "这份摘要主要用于哪种场景？",
    reason: "用途会影响结论的详略和表达方式。",
    options: [
      { value: "review", label: "团队复盘", description: "保留过程、风险和下一步" },
      { value: "brief", label: "管理层简报", description: "突出结果、风险和决策点" },
    ],
    allow_free_text: true,
  },
};

const labApproval: ApprovalItem = {
  id: "lab-approval", type: "approval", session_id: "lab-session", run_id: "lab-run",
  sequence: 10, revision: 1, status: "waiting", created_at: "2026-08-26T08:07:00Z",
  payload: {
    version: 1,
    risk_level: "warning",
    reason: "该操作会把生成的摘要写入项目目录。",
    requested_action: { name: "workspace.write_file", arguments: { path: "reports/monthly-summary.md" } },
  },
};

export function DesignLab() {
  const [section, setSection] = useState<LabSection>("compare");
  const [prompt, setPrompt] = useState("分析近 30 天订单转化率，并找出异常渠道");
  const [idlePrompt, setIdlePrompt] = useState("");
  const [runningPrompt, setRunningPrompt] = useState("补充比较自然流量和付费流量");
  const [deliveryMode, setDeliveryMode] = useState<"queue" | "steer" | "cancel_and_replace">("queue");
  const { theme, toggle } = useTheme();

  return (
    <main className="design-lab">
      <header className="design-lab__topbar">
        <div>
          <h1>DBFox Design Lab</h1>
          <span>固定数据 · Core 视觉合同</span>
        </div>
        <div className="design-lab__top-actions">
          <div className="design-lab__segmented" aria-label="预览区域">
            <button type="button" className={section === "compare" ? "is-active" : ""} onClick={() => setSection("compare")}>A/B/C</button>
            <button type="button" className={section === "shell" ? "is-active" : ""} onClick={() => setSection("shell")}>Core Shell</button>
            <button type="button" className={section === "agent" ? "is-active" : ""} onClick={() => setSection("agent")}>Agent UI</button>
            <button type="button" className={section === "surface" ? "is-active" : ""} onClick={() => setSection("surface")}>Work Surface</button>
            <button type="button" className={section === "settings" ? "is-active" : ""} onClick={() => setSection("settings")}>Settings</button>
          </div>
          <Button type="button" variant="outline" size="icon-sm" onClick={toggle} aria-label="切换主题">
            {theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
          </Button>
        </div>
      </header>

      {section === "compare" ? <ComponentComparison /> : null}

      {section === "shell" ? (
        <section className="design-lab__canvas design-lab__shell" aria-label="Core Shell 预览">
          <Sidebar className="design-lab__sidebar" aria-label="主导航预览">
            <SidebarHeader>
              <SidebarNavRow icon={<Plus />} label="新任务" className="design-lab__new-task" />
              <SidebarNavRow icon={<Home />} label="主页" active />
            </SidebarHeader>
            <SidebarContent>
              <SidebarGroup>
                <SidebarGroupLabel action={<Button type="button" variant="ghost" size="icon-sm" aria-label="新建项目"><Plus size={14} /></Button>}>项目</SidebarGroupLabel>
                <SidebarNavRow icon={<Folder />} label="增长分析" meta="12" />
                <SidebarNavRow icon={<Folder />} label="供应链" meta="4" />
              </SidebarGroup>
              <SidebarGroup>
                <SidebarGroupLabel>最近工作</SidebarGroupLabel>
                <SidebarNavRow icon={<MessageSquare />} label="渠道转化率异常排查" meta="2m" />
                <SidebarNavRow icon={<MessageSquare />} label="华东库存周转分析" meta="1h" />
                <SidebarNavRow icon={<MessageSquare />} label="留存 cohort 复盘" meta="昨天" />
                <SidebarNavRow icon={<MessageSquare />} label="月度经营摘要" meta="周一" />
                <SidebarNavRow icon={<MessageSquare />} label="交付风险清单" meta="周一" />
                <SidebarNavRow icon={<MessageSquare />} label="客户反馈主题整理" meta="8月18日" />
                <SidebarNavRow icon={<MessageSquare />} label="下季度目标草案" meta="8月15日" />
                <SidebarNavRow icon={<MessageSquare />} label="跨团队依赖核对" meta="8月12日" />
              </SidebarGroup>
            </SidebarContent>
            <SidebarFooter>
              <SidebarNavRow icon={<PackageOpen />} label="扩展" />
              <SidebarNavRow icon={<Settings />} label="设置" />
            </SidebarFooter>
          </Sidebar>

          <div className="design-lab__home">
            <div className="design-lab__home-copy">
              <span className="design-lab__eyebrow">增长分析</span>
              <h1>今天要完成什么？</h1>
              <p>描述目标，DBFox 会调用项目中的数据和工具完成任务。</p>
            </div>
            <UnifiedComposer
              value={prompt}
              onChange={setPrompt}
              onSubmit={() => undefined}
              references={[{ label: "analytics.orders", object: { kind: "table", id: "analytics.orders" } }]}
              onRemoveReference={() => undefined}
              placeholder="询问数据、生成分析或处理文件…"
              ariaLabel="Design Lab 输入框"
            />
            <div className="design-lab__recent">
              <div className="design-lab__section-heading"><span>最近工作</span><button type="button">查看全部</button></div>
              <LabRecent title="渠道转化率异常排查" summary="对比 7 个获客渠道，定位到两个异常变化。" time="2 分钟前" />
              <LabRecent title="华东库存周转分析" summary="已生成结果表和三项补货建议。" time="1 小时前" />
            </div>
          </div>
        </section>
      ) : null}

      {section === "agent" ? (
        <section className="design-lab__canvas design-lab__agent" aria-label="Agent UI 预览">
          <div className="design-lab__conversation">
            <div className="design-lab__fixture">
              <span className="design-lab__fixture-label">Composer · 空闲</span>
              <UnifiedComposer
                value={idlePrompt}
                onChange={setIdlePrompt}
                onSubmit={() => undefined}
                  placeholder="描述要完成的工作…"
                ariaLabel="空闲输入框"
                compact
              />
            </div>
            <div className="design-lab__fixture">
              <span className="design-lab__fixture-label">对话 · 工具组 · 计划 · 最终回答</span>
              <AgentTimeline ariaLabel="已完成任务时间线" run={labRun} items={labItems} artifacts={[]} />
            </div>
            <div className="design-lab__fixture">
              <span className="design-lab__fixture-label">流式回答</span>
              <AgentTimeline ariaLabel="流式回答时间线" run={streamingRun} items={streamingItems} artifacts={[]} />
            </div>
            <div className="design-lab__fixture">
              <span className="design-lab__fixture-label">数据来源 · 原生渐进披露</span>
              <Sources className="conv-data-refs">
                <SourcesTrigger count={2} aria-label="引用的数据来源，2 项" />
                <SourcesContent className="conv-data-ref-list">
                  <span className="conv-data-ref conv-data-ref-result">
                    <Database size={14} aria-hidden="true" />
                    <span>订单明细结果</span>
                  </span>
                  <span className="conv-data-ref conv-data-ref-chart">
                    <GitBranch size={14} aria-hidden="true" />
                    <span>月度趋势图</span>
                  </span>
                </SourcesContent>
              </Sources>
            </div>
            <AgentQuestion question={labQuestion} onRespond={() => undefined} />
            <div className="design-lab__state-grid">
              <ApprovalCard approval={labApproval} onResolve={() => undefined} />
              <div className="design-lab__error" role="alert">
                <CircleAlert size={16} />
                <span><strong>结果加载失败</strong><small>连接已断开，请重试。</small></span>
                <Button type="button" variant="outline" size="sm">重试</Button>
              </div>
            </div>
            <UnifiedComposer
              value={runningPrompt}
              onChange={setRunningPrompt}
              onSubmit={() => undefined}
              placeholder="继续追问…"
              ariaLabel="运行中输入框"
              running
              deliveryMode={deliveryMode}
              onDeliveryModeChange={setDeliveryMode}
              onCancel={() => undefined}
            />
          </div>
        </section>
      ) : null}

      {section === "surface" ? (
        <section className="design-lab__canvas design-lab__surface" aria-label="Work Surface 预览">
          <div className="design-lab__surface-shell">
            <header className="design-lab__surface-tabs">
              <button type="button" className="is-active"><Database size={16} /><span>渠道转化结果</span><X size={14} /></button>
              <button type="button"><FileCode2 size={16} /><span>analysis.sql</span><X size={14} /></button>
              <div className="design-lab__surface-spacer" />
              <button type="button" aria-label="工作区全屏"><Maximize2 size={16} /></button>
              <button type="button" aria-label="收起工作区"><PanelRightClose size={16} /></button>
            </header>
            <div className="design-lab__surface-body">
              <div className="design-lab__surface-content">
                <nav className="design-lab__tree" aria-label="数据对象">
                  <strong>analytics</strong>
                  <button type="button"><ChevronDown size={14} /><Database size={14} />public</button>
                  <button type="button" className="is-active"><span /><FileCode2 size={14} />orders</button>
                  <button type="button"><span /><FileCode2 size={14} />sessions</button>
                  <button type="button"><span /><FileCode2 size={14} />channels</button>
                </nav>
                <div className="design-lab__table-wrap">
                  <table>
                    <thead><tr><th>渠道</th><th>访问</th><th>订单</th><th>转化率</th><th>环比</th></tr></thead>
                    <tbody>
                      <tr><td>自然搜索</td><td>48,230</td><td>2,214</td><td>4.59%</td><td className="is-positive">+0.22%</td></tr>
                      <tr><td>信息流广告</td><td>36,104</td><td>1,008</td><td>2.79%</td><td className="is-negative">−1.31%</td></tr>
                      <tr><td>联盟渠道</td><td>18,720</td><td>562</td><td>3.00%</td><td className="is-negative">−0.86%</td></tr>
                      <tr><td>直接访问</td><td>14,892</td><td>741</td><td>4.98%</td><td className="is-positive">+0.14%</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <footer><GitBranch size={14} /><span>数据来源：analytics.orders · 查询已校验 · 7 行</span><Clock3 size={14} /><span>428 ms</span></footer>
            </div>
          </div>
        </section>
      ) : null}

      {section === "settings" ? (
        <section className="design-lab__canvas design-lab__settings" aria-label="设置预览">
          <nav>
            <strong>设置</strong>
            <button type="button" className="is-active">外观</button>
            <button type="button">模型</button>
            <button type="button">扩展</button>
            <button type="button">更新</button>
          </nav>
          <div className="design-lab__settings-page">
            <header><h1>外观</h1><p>这些设置仅影响本机显示。</p></header>
            <section><div><strong>主题</strong><span>选择浅色、深色或跟随系统。</span></div><div className="design-lab__segmented"><button type="button" className={theme === "light" ? "is-active" : ""}>浅色</button><button type="button" className={theme === "dark" ? "is-active" : ""}>深色</button></div></section>
            <section>
              <div><strong>界面密度</strong><span>默认密度适合桌面分析工作。</span></div>
              <Select defaultValue="default">
                <SelectTrigger aria-label="界面密度"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="compact">紧凑</SelectItem>
                  <SelectItem value="default">默认</SelectItem>
                  <SelectItem value="comfortable">宽松</SelectItem>
                </SelectContent>
              </Select>
            </section>
            <section><div><strong>强调色</strong><span>用于当前项、焦点和主要操作。</span></div><div className="design-lab__swatches"><button type="button" className="is-active" aria-label="蓝色" /><button type="button" aria-label="青色" /><button type="button" aria-label="绿色" /></div></section>
            <footer><Button type="button" variant="outline">恢复默认</Button><Button type="button">保存设置</Button></footer>
          </div>
        </section>
      ) : null}
    </main>
  );
}

function LabRecent({ title, summary, time }: { title: string; summary: string; time: string }) {
  return (
    <button type="button" className="design-lab__recent-row">
      <MessageSquare size={16} aria-hidden="true" />
      <span><strong>{title}</strong><small>{summary}</small></span>
      <time>{time}</time>
    </button>
  );
}
