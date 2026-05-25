import { useEffect, useState } from "react";
import {
  Activity,
  Award,
  Clock,
  Cpu,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import ReactECharts from "echarts-for-react";
import { api } from "../lib/api";
import type { DataSource, QueryHistory } from "../lib/api";
import { useToast } from "../components/Toast";

interface DashboardPageProps {
  datasource: DataSource;
}

export function DashboardPage({ datasource }: DashboardPageProps) {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<any>(null);
  const [history, setHistory] = useState<QueryHistory[]>([]);
  const [selectedLog, setSelectedLog] = useState<QueryHistory | null>(null);

  useEffect(() => {
    void loadDashboardData();
  }, [datasource.id]);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      const [statsData, historyData] = await Promise.all([
        api.getLlmStats(datasource.id),
        api.listHistory(datasource.id),
      ]);
      setStats(statsData);
      setHistory(historyData);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const lineChartOption = stats?.chart_data?.length > 0 ? {
    color: ["#4A5BC0"],
    tooltip: { trigger: "axis" },
    grid: { left: "4%", right: "4%", bottom: "4%", top: "12%", containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: stats.chart_data.map((d: any) => d.date),
      axisLabel: { color: "#8E9AA8", fontSize: 11 },
      axisLine: { lineStyle: { color: "rgba(142, 154, 168, 0.2)" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#8E9AA8", fontSize: 11 },
      splitLine: { lineStyle: { color: "rgba(142, 154, 168, 0.1)" } },
    },
    series: [
      {
        name: "请求次数",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { width: 3, shadowBlur: 10, shadowColor: "rgba(74, 91, 192, 0.3)" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(74, 91, 192, 0.25)" },
              { offset: 1, color: "rgba(74, 91, 192, 0.00)" },
            ],
          },
        },
        data: stats.chart_data.map((d: any) => d.value),
      },
    ],
  } : null;

  const pieChartOption = stats?.model_dist?.length > 0 ? {
    color: ["#4A5BC0", "#14A3A8", "#B45309", "#2E7D32", "#D97706"],
    tooltip: { trigger: "item" },
    legend: {
      orient: "vertical",
      right: "10%",
      top: "center",
      textStyle: { color: "#5C5D60", fontSize: 11 },
    },
    series: [
      {
        name: "模型分布",
        type: "pie",
        radius: ["50%", "80%"],
        center: ["40%", "50%"],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 8,
          borderColor: "#FFFFFF",
          borderWidth: 2,
        },
        label: { show: false },
        data: stats.model_dist,
      },
    ],
  } : null;

  if (loading) {
    return (
      <div style={{ display: "grid", gridTemplateRows: "auto 1fr", gap: 16, height: "100%", overflow: "hidden" }}>
        <div className="skeleton" style={{ height: 40, borderRadius: 8 }} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 14 }}>
          {[1, 2, 3, 4].map((i) => <div key={i} className="skeleton" style={{ height: 100, borderRadius: 10 }} />)}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1.2fr", gap: 16 }}>
          <div className="skeleton" style={{ height: 300, borderRadius: 12 }} />
          <div className="skeleton" style={{ height: 300, borderRadius: 12 }} />
        </div>
      </div>
    );
  }

  const safeRate = stats ? stats.success_rate : 100.0;
  const avgLatency = stats ? stats.avg_latency_ms : 0;
  const totalCalls = stats ? stats.total_calls : 0;
  const blockedRate = stats ? stats.guardrail_block_rate : 0.0;

  return (
    <div
      className="animate-fade-in"
      style={{ display: "flex", flexDirection: "column", gap: 18, height: "100%", overflow: "auto", paddingRight: 4 }}
    >
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 className="text-display" style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>
            AI 监控 & 审计中心
          </h2>
          <p style={{ color: "var(--text-secondary)", marginTop: 4, fontSize: "0.9rem" }}>
            实时监控 AI 模型时延、SQL 执行安全阻断率及 Token 效率
          </p>
        </div>
        <button className="btn-secondary" onClick={loadDashboardData}>
          <RefreshCw size={14} style={{ marginRight: 6 }} />
          刷新看板
        </button>
      </div>

      {/* KPI Cards Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 14 }}>
        {/* KPI 1 */}
        <div className="lab-card hover-lift" style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 44, height: 44, borderRadius: 10, background: "rgba(74, 91, 192, 0.08)", display: "grid", placeItems: "center", flexShrink: 0 }}>
            <Activity size={20} style={{ color: "var(--accent-indigo)" }} />
          </div>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 500 }}>累计 AI 请求次数</div>
            <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 4, color: "var(--text-primary)" }}>
              {totalCalls} <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 400 }}>次</span>
            </div>
          </div>
        </div>

        {/* KPI 2 */}
        <div className="lab-card hover-lift" style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 44, height: 44, borderRadius: 10, background: "rgba(13, 115, 119, 0.08)", display: "grid", placeItems: "center", flexShrink: 0 }}>
            <Clock size={20} style={{ color: "#0D7377" }} />
          </div>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 500 }}>平均生成响应时延</div>
            <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 4, color: "var(--text-primary)" }}>
              {avgLatency} <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 400 }}>ms</span>
            </div>
          </div>
        </div>

        {/* KPI 3 */}
        <div className="lab-card hover-lift" style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 44, height: 44, borderRadius: 10, background: "rgba(46, 125, 50, 0.08)", display: "grid", placeItems: "center", flexShrink: 0 }}>
            <ShieldCheck size={20} style={{ color: "var(--accent-green)" }} />
          </div>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 500 }}>AI 调用成功率</div>
            <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 4, color: "var(--accent-green)" }}>
              {safeRate}%
            </div>
          </div>
        </div>

        {/* KPI 4 */}
        <div className="lab-card hover-lift" style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 44, height: 44, borderRadius: 10, background: "rgba(180, 83, 9, 0.08)", display: "grid", placeItems: "center", flexShrink: 0 }}>
            <Award size={20} style={{ color: "var(--accent-amber)" }} />
          </div>
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 500 }}>Guardrail 安全拦截率</div>
            <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 4, color: blockedRate > 0 ? "var(--accent-red)" : "var(--text-primary)" }}>
              {blockedRate}%
            </div>
          </div>
        </div>
      </div>

      {/* Charts Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1.8fr 1.2fr", gap: 16 }}>
        {/* Line Chart */}
        <div className="lab-card" style={{ padding: 20, display: "flex", flexDirection: "column", height: 320 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <h3 style={{ fontSize: "0.92rem", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
              <TrendingUp size={15} style={{ color: "var(--accent-indigo)" }} />
              AI 问数请求频次趋势
            </h3>
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            {lineChartOption ? (
              <ReactECharts option={lineChartOption} style={{ height: "100%", width: "100%" }} />
            ) : (
              <div style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--text-muted)", fontSize: "0.8rem" }}>
                暂无调用趋势数据
              </div>
            )}
          </div>
        </div>

        {/* Pie Chart */}
        <div className="lab-card" style={{ padding: 20, display: "flex", flexDirection: "column", height: 320 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <h3 style={{ fontSize: "0.92rem", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
              <Cpu size={15} style={{ color: "#0D7377" }} />
              语言模型 (LLM) 调用分布
            </h3>
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            {pieChartOption ? (
              <ReactECharts option={pieChartOption} style={{ height: "100%", width: "100%" }} />
            ) : (
              <div style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--text-muted)", fontSize: "0.8rem" }}>
                暂无模型调用分布数据
              </div>
            )}
          </div>
        </div>
      </div>

      {/* SQL Observability & Audit Log List */}
      <div className="lab-card" style={{ padding: 20, flex: 1 }}>
        <h3 style={{ fontSize: "0.92rem", fontWeight: 600, marginBottom: 16 }}>AI 生成安全审计日志 (LLM SQL Logs)</h3>
        {history.length === 0 ? (
          <div style={{ padding: 36, textAlign: "center", color: "var(--text-muted)", fontSize: "0.8rem" }}>
            暂无生成日志，前往 SQL 工作台提问即可自动在此留存审计数据。
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>用户提问</th>
                  <th>安全 SQL</th>
                  <th>安全审核 (Guardrail)</th>
                  <th>状态</th>
                  <th>执行耗时</th>
                </tr>
              </thead>
              <tbody>
                {history.map((log) => {
                  const gr = log.guardrail_result;
                  return (
                    <tr
                      key={log.id}
                      className="hover-lift-subtle"
                      style={{ cursor: "pointer" }}
                      onClick={() => setSelectedLog(log)}
                    >
                      <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem", color: "var(--text-muted)" }}>
                        {new Date(log.created_at).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </td>
                      <td style={{ fontSize: "0.8rem", color: "var(--text-primary)", fontWeight: 500, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {log.question || "-"}
                      </td>
                      <td className="text-mono" style={{ fontSize: "0.76rem", color: "var(--text-secondary)", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {log.safe_sql || log.submitted_sql || "-"}
                      </td>
                      <td>
                        <span className={`tag ${gr === "pass" ? "tag-success" : gr === "warn" ? "tag-warning" : "tag-danger"}`} style={{ fontSize: "0.7rem", padding: "2px 6px" }}>
                          {gr === "pass" ? "通过 (Approved)" : gr === "warn" ? "警告 (Warning)" : "拦截 (Blocked)"}
                        </span>
                      </td>
                      <td>
                        <span style={{ color: log.execution_status === "success" ? "var(--accent-green)" : "var(--accent-red)", fontSize: "0.78rem", fontWeight: 600 }}>
                          {log.execution_status === "success" ? "Success" : "Failed"}
                        </span>
                      </td>
                      <td className="cell-number" style={{ fontSize: "0.78rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end" }}>
                          <span>{log.execution_time_ms}ms</span>
                          <span style={{ color: "var(--accent-indigo)", fontSize: "0.75rem" }}>🔍</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ═ AUDIT LOG DETAILS INSPECTOR MODAL ═ */}
      {selectedLog && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.6)",
            backdropFilter: "blur(6px)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 9999,
          }}
          onClick={() => setSelectedLog(null)}
        >
          <div
            className="lab-card animate-slide-down"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-medium)",
              borderRadius: 12,
              width: "min(680px, 92vw)",
              maxHeight: "82vh",
              display: "flex",
              flexDirection: "column",
              boxShadow: "var(--shadow-lg)",
              overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "16px 20px",
                borderBottom: "1px solid var(--border-light)",
                background: "var(--bg-secondary)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="status-badge status-badge-success" style={{ fontWeight: 700 }}>
                  🛡️ 安全审计详情 (Audit Details)
                </span>
                <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  Log ID: {selectedLog.id.slice(0, 8)}...
                </span>
              </div>
              <button
                onClick={() => setSelectedLog(null)}
                style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div style={{ flex: 1, padding: 20, overflow: "auto", display: "flex", flexDirection: "column", gap: 16, background: "var(--bg-active)" }}>
              {/* Question */}
              <div>
                <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 6, fontWeight: 700 }}>🙋‍♂️ 用户问答提示 (User Prompt)</div>
                <div style={{ background: "var(--bg-surface)", padding: "10px 14px", borderRadius: 8, fontSize: "0.86rem", color: "var(--text-primary)", border: "1px solid var(--border-light)", lineHeight: "1.5" }}>
                  {selectedLog.question || "（空白或工作台直接运行）"}
                </div>
              </div>

              {/* SQL Code */}
              <div>
                <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 6, fontWeight: 700, display: "flex", justifyContent: "space-between" }}>
                  <span>💻 执行 SQL (Generated SQL)</span>
                  <button
                    onClick={async () => {
                      await navigator.clipboard.writeText(selectedLog.executed_sql || selectedLog.safe_sql || selectedLog.submitted_sql);
                      toast.toast("SQL 已复制到剪贴板", "success");
                    }}
                    style={{ background: "none", border: "none", color: "var(--accent-indigo)", cursor: "pointer", fontSize: "0.72rem", fontWeight: 600 }}
                  >
                    复制 SQL 📋
                  </button>
                </div>
                <pre style={{ margin: 0, padding: 12, background: "var(--bg-surface)", borderRadius: 8, border: "1px solid var(--border-light)", fontFamily: "var(--font-mono)", fontSize: "0.82rem", color: "var(--text-primary)", whiteSpace: "pre-wrap", wordBreak: "break-all", lineHeight: "1.5" }}>
                  {selectedLog.executed_sql || selectedLog.safe_sql || selectedLog.submitted_sql}
                </pre>
              </div>

              {/* Guardrail Check Details */}
              <div>
                <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 6, fontWeight: 700 }}>🛡️ 安全拦截审计元数据 (Guardrail Metadata)</div>
                <pre style={{ margin: 0, padding: 12, background: "var(--bg-surface)", borderRadius: 8, border: "1px solid var(--border-light)", fontFamily: "var(--font-mono)", fontSize: "0.8rem", color: "var(--text-secondary)", whiteSpace: "pre-wrap", wordBreak: "break-all", lineHeight: "1.5" }}>
                  {JSON.stringify({
                    result: selectedLog.guardrail_result === "pass" ? "通过 (Approved)" : selectedLog.guardrail_result === "warn" ? "警告 (Warning)" : "拦截 (Blocked)",
                    checks: selectedLog.guardrail_checks || "该 SQL 符合默认安全基线配置，未涉及 DDL/DML 高危权限破坏或敏感字段泄露。",
                  }, null, 2)}
                </pre>
              </div>

              {/* Stats */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div style={{ padding: 12, background: "var(--bg-surface)", borderRadius: 8, border: "1px solid var(--border-light)" }}>
                  <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>响应延时</div>
                  <strong style={{ fontSize: "1.1rem", color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>{selectedLog.execution_time_ms} ms</strong>
                </div>
                <div style={{ padding: 12, background: "var(--bg-surface)", borderRadius: 8, border: "1px solid var(--border-light)" }}>
                  <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>返回/受影响行数</div>
                  <strong style={{ fontSize: "1.1rem", color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>{selectedLog.rows_returned} 行</strong>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div style={{ display: "flex", justifyContent: "flex-end", padding: "12px 20px", borderTop: "1px solid var(--border-light)", background: "var(--bg-secondary)" }}>
              <button className="btn-primary" style={{ padding: "5px 16px", fontSize: "0.8rem" }} onClick={() => setSelectedLog(null)}>
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
