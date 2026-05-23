import React, { useState, useEffect } from "react";
import { Award, X } from "lucide-react";
import { api } from "../lib/api";
import type { DataSource } from "../lib/api";

interface AiBenchmarkDrawerProps {
  datasource: DataSource;
  aiConfig: {
    apiKey: string;
    apiBase: string;
    model: string;
    optimizeRag: boolean;
  };
  initialQuestion?: string;
  initialSql?: string;
  onClose: () => void;
}

export const AiBenchmarkDrawer: React.FC<AiBenchmarkDrawerProps> = ({
  datasource,
  aiConfig,
  initialQuestion = "",
  initialSql = "",
  onClose,
}) => {
  const [goldenSqls, setGoldenSqls] = useState<any[]>([]);
  const [benchmarkRunning, setBenchmarkRunning] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState<any | null>(null);
  const [goldenQuestion, setGoldenQuestion] = useState(initialQuestion);
  const [goldenSqlText, setGoldenSqlText] = useState(initialSql);
  const [addingGolden, setAddingGolden] = useState(false);

  useEffect(() => {
    void fetchGoldenSqls();
  }, [datasource.id]);

  // Sync initial presets if they change from parent actions
  useEffect(() => {
    if (initialQuestion) setGoldenQuestion(initialQuestion);
    if (initialSql) setGoldenSqlText(initialSql);
  }, [initialQuestion, initialSql]);

  const fetchGoldenSqls = async () => {
    try {
      const items = await api.listGoldenSql(datasource.id);
      setGoldenSqls(items);
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateGoldenSql = async () => {
    if (!goldenQuestion.trim() || !goldenSqlText.trim()) return;
    try {
      setAddingGolden(true);
      await api.createGoldenSql(datasource.id, goldenQuestion.trim(), goldenSqlText.trim());
      setGoldenQuestion("");
      setGoldenSqlText("");
      await fetchGoldenSqls();
    } catch (e: any) {
      alert(e.message || "添加失败");
    } finally {
      setAddingGolden(false);
    }
  };

  const handleDeleteGolden = async (id: string) => {
    if (!window.confirm("确定删除这个黄金测试句？")) return;
    try {
      await api.deleteGoldenSql(id);
      await fetchGoldenSqls();
    } catch (e: any) {
      alert(e.message || "删除失败");
    }
  };

  const handleRunBenchmark = async () => {
    try {
      setBenchmarkRunning(true);
      setBenchmarkResult(null);
      const res = await api.runBenchmark(datasource.id, {
        apiKey: aiConfig.apiKey || undefined,
        apiBase: aiConfig.apiBase || undefined,
        model: aiConfig.model || undefined,
        optimizeRag: aiConfig.optimizeRag,
      });
      setBenchmarkResult(res);
    } catch (e: any) {
      alert(e.message || "运行评估失败");
    } finally {
      setBenchmarkRunning(false);
    }
  };

  return (
    <div
      className="animate-fade-in"
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        width: "600px",
        height: "100vh",
        background: "rgba(255, 255, 255, 0.98)",
        backdropFilter: "blur(20px)",
        boxShadow: "-10px 0 30px rgba(0, 0, 0, 0.08)",
        borderLeft: "1px solid var(--border-light)",
        zIndex: 1000,
        display: "grid",
        gridTemplateRows: "auto minmax(0, 1fr)",
        padding: "24px",
        color: "var(--text-primary)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 20,
          borderBottom: "1px solid var(--border-light)",
          paddingBottom: 14,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: 8,
              background: "rgba(74, 91, 192, 0.1)",
              display: "grid",
              placeItems: "center",
            }}
          >
            <Award size={18} style={{ color: "var(--accent-indigo)" }} />
          </div>
          <div>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>黄金测试集 & AI Benchmark</h3>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 2 }}>
              运行回归测试，智能评估 AI 生成的准确度
            </p>
          </div>
        </div>
        <button className="btn-ghost" onClick={onClose} style={{ padding: 6 }}>
          <X size={18} />
        </button>
      </div>

      {/* Scrollable Content */}
      <div
        style={{
          overflow: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 18,
          paddingRight: 4,
          paddingBottom: 24,
        }}
      >
        {/* Create Golden SQL Box */}
        <div className="lab-card" style={{ padding: 16 }}>
          <h4 style={{ fontSize: "0.88rem", fontWeight: 600, marginBottom: 12, color: "var(--text-primary)" }}>
            添加黄金 SQL 对
          </h4>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div>
              <label className="field-label">自然语言提问</label>
              <input
                className="input-field input-field-sm"
                value={goldenQuestion}
                onChange={(e) => setGoldenQuestion(e.target.value)}
                placeholder="例：查询订单金额排名前五的客户ID"
              />
            </div>
            <div>
              <label className="field-label">标准 Golden SQL 语句</label>
              <textarea
                className="input-field"
                style={{
                  minHeight: 60,
                  fontSize: "0.8rem",
                  fontFamily: "var(--font-mono)",
                  padding: 8,
                  resize: "vertical",
                }}
                value={goldenSqlText}
                onChange={(e) => setGoldenSqlText(e.target.value)}
                placeholder="SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id ORDER BY SUM(amount) DESC LIMIT 5;"
              />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                className="btn-primary"
                style={{ padding: "5px 14px", fontSize: "0.78rem" }}
                onClick={handleCreateGoldenSql}
                disabled={addingGolden}
              >
                保存至测试集
              </button>
            </div>
          </div>
        </div>

        {/* Run Benchmark Actions */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "var(--bg-secondary)",
            padding: "12px 16px",
            borderRadius: 10,
            border: "1px solid var(--border-light)",
          }}
        >
          <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
            已保存测试用例：<strong>{goldenSqls.length}</strong> 个
          </div>
          <button
            className="btn-primary shadow-md hover-lift"
            style={{ padding: "6px 16px", fontSize: "0.84rem", background: "var(--accent-indigo)" }}
            onClick={handleRunBenchmark}
            disabled={benchmarkRunning || goldenSqls.length === 0}
          >
            {benchmarkRunning ? "测试运行中..." : "一键运行 Benchmark 评估"}
          </button>
        </div>

        {/* Benchmark Results */}
        {benchmarkRunning && (
          <div className="lab-card animate-pulse" style={{ padding: 24, textAlign: "center" }}>
            <div style={{ fontSize: "0.88rem", color: "var(--text-secondary)", marginBottom: 12 }}>
              正在通过 AST + 结果集交叉校验中...
            </div>
            <div
              style={{
                width: "100%",
                height: 6,
                background: "var(--bg-secondary)",
                borderRadius: 3,
                overflow: "hidden",
                position: "relative",
              }}
            >
              <div
                className="progress-bar-glow"
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  height: "100%",
                  width: "70%",
                  background: "var(--accent-indigo)",
                  borderRadius: 3,
                }}
              />
            </div>
          </div>
        )}

        {benchmarkResult && !benchmarkRunning && (
          <div className="animate-slide-down" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Stats Summary Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
              <div className="lab-card" style={{ padding: 14, textAlign: "center" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>通过率 (Accuracy)</div>
                <div
                  style={{
                    fontSize: "1.4rem",
                    fontWeight: 700,
                    color: benchmarkResult.accuracy_rate >= 80 ? "var(--accent-green)" : "var(--accent-amber)",
                    marginTop: 4,
                  }}
                >
                  {benchmarkResult.accuracy_rate}%
                </div>
              </div>
              <div className="lab-card" style={{ padding: 14, textAlign: "center" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>测试用例总数</div>
                <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--text-primary)", marginTop: 4 }}>
                  {benchmarkResult.total_queries}{" "}
                  <span style={{ fontSize: "0.8rem", fontWeight: 500, color: "var(--text-muted)" }}>
                    ({benchmarkResult.passed_count} 通)
                  </span>
                </div>
              </div>
              <div className="lab-card" style={{ padding: 14, textAlign: "center" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>平均生成时延</div>
                <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--text-primary)", marginTop: 4 }}>
                  {benchmarkResult.avg_latency_ms}ms
                </div>
              </div>
            </div>

            {/* Benchmark details cards */}
            <div>
              <h4 style={{ fontSize: "0.84rem", fontWeight: 600, marginBottom: 8, color: "var(--text-secondary)" }}>
                回归细节清单
              </h4>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {benchmarkResult.details.map((detail: any, i: number) => {
                  const passed = detail.status === "passed";
                  return (
                    <div
                      key={i}
                      className="lab-card"
                      style={{
                        padding: 14,
                        borderLeft: `3px solid ${passed ? "var(--accent-green)" : "var(--accent-red)"}`,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: "0.82rem",
                            color: "var(--text-primary)",
                            maxWidth: "80%",
                            wordBreak: "break-all",
                          }}
                        >
                          Q: "{detail.question}"
                        </div>
                        <span
                          className={`tag ${passed ? "tag-success" : "tag-danger"}`}
                          style={{ fontSize: "0.7rem", padding: "2px 6px", whiteSpace: "nowrap" }}
                        >
                          {passed
                            ? `通过 (${detail.match_type === "lexical" ? "句法匹配" : "等值执行"})`
                            : "失败"}
                        </span>
                      </div>

                      <div
                        style={{
                          marginTop: 8,
                          display: "grid",
                          gridTemplateColumns: "1fr 1fr",
                          gap: 10,
                          fontSize: "0.75rem",
                          fontFamily: "var(--font-mono)",
                          background: "var(--bg-secondary)",
                          padding: 8,
                          borderRadius: 6,
                        }}
                      >
                        <div>
                          <div style={{ color: "var(--text-muted)", marginBottom: 3 }}>Golden SQL (标准):</div>
                          <div style={{ color: "var(--text-secondary)", wordBreak: "break-all" }}>
                            {detail.golden_sql}
                          </div>
                        </div>
                        <div>
                          <div style={{ color: "var(--text-muted)", marginBottom: 3 }}>
                            Generated SQL (AI 生成):
                          </div>
                          <div style={{ color: passed ? "var(--text-secondary)" : "var(--accent-red)", wordBreak: "break-all" }}>
                            {detail.generated_sql || "(无生成)"}
                          </div>
                        </div>
                      </div>

                      {!passed && detail.error_message && (
                        <div
                          style={{
                            marginTop: 6,
                            fontSize: "0.74rem",
                            color: "var(--accent-red)",
                            background: "rgba(220, 38, 38, 0.05)",
                            border: "1px solid rgba(220, 38, 38, 0.1)",
                            padding: "6px 10px",
                            borderRadius: 4,
                          }}
                        >
                          阻碍：{detail.error_message}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Existing Golden SQL List */}
        <div>
          <h4 style={{ fontSize: "0.86rem", fontWeight: 600, marginBottom: 8, color: "var(--text-secondary)" }}>
            用例库 ({goldenSqls.length})
          </h4>
          {goldenSqls.length === 0 ? (
            <div
              style={{
                fontSize: "0.8rem",
                color: "var(--text-muted)",
                padding: "12px",
                border: "1px dashed var(--border-light)",
                borderRadius: 8,
                textAlign: "center",
              }}
            >
              暂无测试用例，请在上方添加或在工作台将有效 SQL “另存为 Golden SQL”
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {goldenSqls.map((pair) => (
                <div
                  key={pair.id}
                  className="lab-card"
                  style={{
                    padding: "10px 14px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 16,
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: "0.8rem", color: "var(--text-primary)" }}>
                      Q: "{pair.question}"
                    </div>
                    <div
                      className="text-mono"
                      style={{
                        fontSize: "0.74rem",
                        color: "var(--text-muted)",
                        marginTop: 2,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {pair.golden_sql}
                    </div>
                  </div>
                  <button
                    className="btn-ghost"
                    onClick={() => handleDeleteGolden(pair.id)}
                    style={{ color: "var(--accent-red)", padding: 4 }}
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
