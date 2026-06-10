import React from "react";
import {
  AlertTriangle,
  BarChart3,
  Clock,
  Download,
  FileCode,
  Sparkles,
  XCircle,
} from "lucide-react";
import type { QueryExecutionPlan } from "../lib/query-actions/types";

interface QueryActionPlanPreviewProps {
  plan: QueryExecutionPlan | null;
}

export const QueryActionPlanPreview: React.FC<QueryActionPlanPreviewProps> = ({ plan }) => {
  if (!plan || plan.actions.length === 0) return null;

  const hasErrors = plan.issues.some((i) => i.level === "error");
  const hasWarnings = plan.issues.some((i) => i.level === "warning");

  return (
    <div className="query-action-plan-preview bg-card border border-border rounded-lg" style={{
      margin: "12px 0",
      padding: 16,
      background: "rgba(30, 30, 34, 0.65)",
      backdropFilter: "blur(12px)",
      border: hasErrors 
        ? "1px solid rgba(239, 68, 68, 0.35)" 
        : hasWarnings 
          ? "1px solid rgba(245, 158, 11, 0.35)" 
          : "1px solid rgba(45, 59, 140, 0.3)",
      borderRadius: 8,
      color: "var(--text-primary)",
      display: "flex",
      flexDirection: "column",
      gap: 12,
      boxShadow: "0 4px 20px rgba(0, 0, 0, 0.15)",
    }}>
      {/* Title */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.85rem", fontWeight: 600 }}>
          <Sparkles size={14} style={{ color: "#4A5BC0" }} />
          <span>注解执行计划预览 (SQL Action Plan)</span>
        </div>
        <span style={{
          fontSize: "0.72rem",
          padding: "2px 6px",
          borderRadius: 4,
          background: hasErrors 
            ? "rgba(239, 68, 68, 0.15)" 
            : hasWarnings 
              ? "rgba(245, 158, 11, 0.15)" 
              : "rgba(46, 125, 50, 0.15)",
          color: hasErrors ? "#EF4444" : hasWarnings ? "#F59E0B" : "#4CAF50",
          fontWeight: 500
        }}>
          {hasErrors ? "校验失败" : hasWarnings ? "警告" : "就绪"}
        </span>
      </div>

      {/* Directives Badges */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {plan.actions.map((act, index) => (
          <span
            key={index}
            style={{
              fontSize: "0.75rem",
              padding: "4px 8px",
              background: "rgba(45, 59, 140, 0.15)",
              border: "1px solid rgba(45, 59, 140, 0.35)",
              borderRadius: 4,
              color: "#A5B4FC",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <strong>@{act.type}</strong>
            <span style={{ opacity: 0.8, fontSize: "0.7rem" }}>({act.label})</span>
          </span>
        ))}
      </div>

      {/* SQL Compilation Diff Panel */}
      {plan.compiledSql !== plan.pureSql && (
        <div style={{
          display: "flex",
          flexDirection: "column",
          gap: 6,
          background: "rgba(20, 20, 22, 0.8)",
          padding: 10,
          borderRadius: 6,
          border: "1px solid rgba(255,255,255,0.05)"
        }}>
          <div style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.4)", display: "flex", alignItems: "center", gap: 4 }}>
            <FileCode size={12} />
            <span>SQL 编译重写对比 (DSL Compile Rewrite)</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.78rem", fontFamily: "Courier New, monospace" }}>
            <div style={{ color: "rgba(255,255,255,0.5)", textDecoration: "line-through", paddingLeft: 4 }}>
              - {plan.pureSql}
            </div>
            <div style={{ color: "#34D399", background: "rgba(52, 211, 153, 0.05)", padding: "2px 4px", borderRadius: 3 }}>
              + {plan.compiledSql}
            </div>
          </div>
        </div>
      )}

      {/* Parameter Summary Panel */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
        gap: 8,
        background: "rgba(0, 0, 0, 0.2)",
        padding: 10,
        borderRadius: 6,
        fontSize: "0.78rem"
      }}>
        {/* Timeout parameter */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Clock size={12} style={{ color: "#9CA3AF" }} />
          <span style={{ color: "rgba(255,255,255,0.4)" }}>执行限时:</span>
          <span style={{ color: "#E5E7EB", fontWeight: 500 }}>{plan.context.timeoutMs / 1000}s</span>
        </div>

        {/* Export parameter */}
        {plan.context.exportConfig?.enabled && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Download size={12} style={{ color: "#34D399" }} />
            <span style={{ color: "rgba(255,255,255,0.4)" }}>导出格式:</span>
            <span style={{ color: "#34D399", fontWeight: 500 }}>
              {plan.context.exportConfig.format.toUpperCase()}
            </span>
          </div>
        )}

        {/* Chart parameter */}
        {plan.context.chartConfig?.enabled && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <BarChart3 size={12} style={{ color: "#60A5FA" }} />
            <span style={{ color: "rgba(255,255,255,0.4)" }}>渲染图表:</span>
            <span style={{ color: "#60A5FA", fontWeight: 500 }}>
              {`${plan.context.chartConfig.type.toUpperCase()}(x=${plan.context.chartConfig.x || "自动"}, y=${plan.context.chartConfig.y || "自动"})`}
            </span>
          </div>
        )}
      </div>

      {/* Plan Validation Diagnostics */}
      {plan.issues.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {plan.issues.map((issue, index) => {
            const isError = issue.level === "error";
            const Icon = isError ? XCircle : AlertTriangle;
            const color = isError ? "#EF4444" : "#F59E0B";
            return (
              <div
                key={index}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 6,
                  padding: "6px 10px",
                  background: isError ? "rgba(239, 68, 68, 0.08)" : "rgba(245, 158, 11, 0.08)",
                  borderRadius: 4,
                  fontSize: "0.78rem",
                  color: color,
                  border: `1px solid ${isError ? "rgba(239,68,68,0.15)" : "rgba(245,158,11,0.15)"}`,
                }}
              >
                <Icon size={14} style={{ marginTop: 2, flexShrink: 0 }} />
                <div>
                  <strong>[@{issue.action || "global"}]</strong> {issue.message}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
