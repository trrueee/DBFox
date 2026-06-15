import { useCallback, useEffect, useState } from "react";
import { FlaskConical, Loader2, Play, Plus, Trash2 } from "lucide-react";
import { getStoredApiConfig } from "../components/SettingsDialog";
import {
  agentEvalApi,
  type AgentEvalCaseResult,
  type AgentEvalRun,
  type AgentGoldenTask,
} from "../lib/api/agentEval";

interface AgentEvalPageProps {
  datasources: Array<{ id: string; name: string }>;
  activeDatasourceId: string;
  onToast: (message: string) => void;
}

export function AgentEvalPage({ datasources, activeDatasourceId, onToast }: AgentEvalPageProps) {
  const [tasks, setTasks] = useState<AgentGoldenTask[]>([]);
  const [runs, setRuns] = useState<AgentEvalRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [expandedRunId, setExpandedRunId] = useState("");
  const [runCases, setRunCases] = useState<Record<string, AgentEvalCaseResult[]>>({});

  const [formName, setFormName] = useState("");
  const [formQuestion, setFormQuestion] = useState("");
  const [formKeywords, setFormKeywords] = useState("");
  const [formSqlRequired, setFormSqlRequired] = useState(true);

  const datasourceName = datasources.find((item) => item.id === activeDatasourceId)?.name || "未选择数据源";

  const refresh = useCallback(async () => {
    if (!activeDatasourceId) {
      setTasks([]);
      setRuns([]);
      return;
    }
    await Promise.resolve();
    setLoading(true);
    try {
      const [nextTasks, nextRuns] = await Promise.all([
        agentEvalApi.listTasks(activeDatasourceId),
        agentEvalApi.listRuns(activeDatasourceId),
      ]);
      setTasks(nextTasks);
      setRuns(nextRuns);
    } catch (err) {
      onToast(err instanceof Error ? err.message : "读取评测数据失败");
    } finally {
      setLoading(false);
    }
  }, [activeDatasourceId, onToast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createTask = async () => {
    const name = formName.trim();
    const question = formQuestion.trim();
    if (!name || !question) {
      onToast("任务名称和问题不能为空");
      return;
    }
    const keywords = formKeywords
      .split(/[,，]/)
      .map((item) => item.trim())
      .filter(Boolean);
    try {
      await agentEvalApi.createTask({
        datasource_id: activeDatasourceId,
        name,
        question,
        expected_final_contains_json: JSON.stringify(keywords),
        expected_sql_required: formSqlRequired,
      });
      setFormName("");
      setFormQuestion("");
      setFormKeywords("");
      setShowForm(false);
      onToast("已创建 Golden 任务");
      await refresh();
    } catch (err) {
      onToast(err instanceof Error ? err.message : "创建任务失败");
    }
  };

  const removeTask = async (taskId: string) => {
    try {
      await agentEvalApi.deleteTask(taskId);
      setTasks((prev) => prev.filter((task) => task.id !== taskId));
      onToast("已删除任务");
    } catch (err) {
      onToast(err instanceof Error ? err.message : "删除任务失败");
    }
  };

  const runEval = async () => {
    if (!activeDatasourceId) {
      onToast("请先选择数据源");
      return;
    }
    if (tasks.length === 0) {
      onToast("当前数据源下没有 Golden 任务，请先创建");
      return;
    }
    const llm = getStoredApiConfig();
    setRunning(true);
    onToast(`开始评测 ${tasks.length} 个任务，请耐心等待…`);
    try {
      const result = await agentEvalApi.runEval({
        datasource_id: activeDatasourceId,
        api_key: llm.apiKey || undefined,
        api_base: llm.apiBase || undefined,
        model_name: llm.modelName || undefined,
        execute: false,
      });
      onToast(`评测完成：${result.passed_cases}/${result.total_cases} 通过`);
      await refresh();
      if (result.id) {
        setExpandedRunId(result.id);
        if (result.case_results?.length) {
          setRunCases((prev) => ({ ...prev, [result.id]: result.case_results || [] }));
        }
      }
    } catch (err) {
      onToast(err instanceof Error ? err.message : "评测运行失败");
    } finally {
      setRunning(false);
    }
  };

  const toggleRun = async (runId: string) => {
    if (expandedRunId === runId) {
      setExpandedRunId("");
      return;
    }
    setExpandedRunId(runId);
    if (!runCases[runId]) {
      try {
        const cases = await agentEvalApi.getRunCases(runId);
        setRunCases((prev) => ({ ...prev, [runId]: cases }));
      } catch (err) {
        onToast(err instanceof Error ? err.message : "读取评测明细失败");
      }
    }
  };

  return (
    <div className="hifi-eval-page">
      <div className="hifi-eval-header">
        <div className="hifi-eval-header-title">
          <FlaskConical size={15} />
          <span>Agent 评测</span>
          <span className="hifi-eval-header-ds">{datasourceName}</span>
        </div>
        <div className="hifi-eval-header-actions">
          <button className="hifi-eval-btn" onClick={() => setShowForm((prev) => !prev)}>
            <Plus size={12} /> 新建任务
          </button>
          <button className="hifi-eval-btn hifi-eval-btn-primary" onClick={() => void runEval()} disabled={running || loading}>
            {running ? <Loader2 size={12} className="hifi-agent-running-spinner" /> : <Play size={12} />}
            {running ? "评测进行中…" : "运行评测"}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="hifi-eval-form">
          <div className="hifi-eval-form-row">
            <label>任务名称</label>
            <input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="例如：按部门统计上月资产数" />
          </div>
          <div className="hifi-eval-form-row">
            <label>问题</label>
            <input value={formQuestion} onChange={(e) => setFormQuestion(e.target.value)} placeholder="输入要让 Agent 回答的自然语言问题" />
          </div>
          <div className="hifi-eval-form-row">
            <label>答案需包含关键词（逗号分隔，可留空）</label>
            <input value={formKeywords} onChange={(e) => setFormKeywords(e.target.value)} placeholder="例如：市场运营部, 资产" />
          </div>
          <div className="hifi-eval-form-row hifi-eval-form-inline">
            <label>
              <input type="checkbox" checked={formSqlRequired} onChange={(e) => setFormSqlRequired(e.target.checked)} />
              要求 Agent 生成 SQL
            </label>
            <button className="hifi-eval-btn hifi-eval-btn-primary" onClick={() => void createTask()}>保存任务</button>
          </div>
        </div>
      )}

      <div className="hifi-eval-body">
        <section className="hifi-eval-panel">
          <div className="hifi-eval-panel-title">Golden 任务（{tasks.length}）</div>
          {loading && tasks.length === 0 ? (
            <div className="hifi-eval-empty">加载中…</div>
          ) : tasks.length === 0 ? (
            <div className="hifi-eval-empty">
              暂无任务。Golden 任务是带有期望结果的标准问题，用于回归验证 Agent 的问答质量。
            </div>
          ) : (
            <ul className="hifi-eval-task-list">
              {tasks.map((task) => (
                <li key={task.id} className="hifi-eval-task">
                  <div className="hifi-eval-task-main">
                    <div className="hifi-eval-task-name">{task.name}</div>
                    <div className="hifi-eval-task-question">{task.question}</div>
                    <div className="hifi-eval-task-meta">
                      {task.expected_sql_required && <span className="hifi-eval-chip">要求 SQL</span>}
                      {parseJsonArray(task.expected_final_contains_json).map((keyword) => (
                        <span key={keyword} className="hifi-eval-chip hifi-eval-chip-keyword">{keyword}</span>
                      ))}
                    </div>
                  </div>
                  <button className="hifi-eval-icon-btn" title="删除任务" onClick={() => void removeTask(task.id)}>
                    <Trash2 size={12} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="hifi-eval-panel">
          <div className="hifi-eval-panel-title">评测历史（{runs.length}）</div>
          {runs.length === 0 ? (
            <div className="hifi-eval-empty">还没有评测记录。点击右上角"运行评测"开始第一次评测。</div>
          ) : (
            <ul className="hifi-eval-run-list">
              {runs.map((run) => {
                const passRate = run.pass_rate !== null && run.pass_rate !== undefined
                  ? `${Math.round(run.pass_rate * 100)}%`
                  : "-";
                const expanded = expandedRunId === run.id;
                return (
                  <li key={run.id} className="hifi-eval-run">
                    <button className="hifi-eval-run-head" onClick={() => void toggleRun(run.id)}>
                      <span className={`hifi-eval-run-rate ${rateClass(run.pass_rate)}`}>{passRate}</span>
                      <span className="hifi-eval-run-counts">{run.passed_cases}/{run.total_cases} 通过</span>
                      {run.avg_latency_ms != null && (
                        <span className="hifi-eval-run-latency">平均 {(run.avg_latency_ms / 1000).toFixed(1)}s</span>
                      )}
                      <span className="hifi-eval-run-time">{formatTime(run.created_at)}</span>
                    </button>
                    {expanded && (
                      <div className="hifi-eval-cases">
                        {(runCases[run.id] || []).map((item) => (
                          <div key={item.id} className="hifi-eval-case">
                            <span className={`hifi-eval-case-status hifi-eval-case-${item.status}`}>
                              {item.status === "passed" ? "通过" : item.status === "failed" ? "未通过" : "错误"}
                            </span>
                            <span className="hifi-eval-case-task">{taskName(tasks, item.task_id)}</span>
                            <span className="hifi-eval-case-score">得分 {item.score.toFixed(2)}</span>
                            {item.latency_ms != null && <span className="hifi-eval-case-latency">{(item.latency_ms / 1000).toFixed(1)}s</span>}
                            {renderFailureReasons(item.failure_reasons_json)}
                          </div>
                        ))}
                        {!runCases[run.id] && <div className="hifi-eval-empty">加载明细中…</div>}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function parseJsonArray(text: string | null | undefined): string[] {
  try {
    const parsed = JSON.parse(text || "[]");
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function taskName(tasks: AgentGoldenTask[], taskId: string): string {
  return tasks.find((task) => task.id === taskId)?.name || taskId.slice(0, 8);
}

function rateClass(passRate: number | null | undefined): string {
  if (passRate === null || passRate === undefined) return "";
  if (passRate >= 0.9) return "hifi-eval-rate-good";
  if (passRate >= 0.6) return "hifi-eval-rate-warn";
  return "hifi-eval-rate-bad";
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return value;
  }
}

function renderFailureReasons(json: string) {
  const reasons = parseJsonArray(json);
  if (reasons.length === 0) return null;
  return (
    <div className="hifi-eval-case-reasons">
      {reasons.map((reason, index) => (
        <div key={index}>· {reason}</div>
      ))}
    </div>
  );
}
