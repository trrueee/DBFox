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

type PlanSeverity = "ready" | "warning" | "error";

function severityFor(plan: QueryExecutionPlan): PlanSeverity {
  if (plan.issues.some((issue) => issue.level === "error")) return "error";
  if (plan.issues.some((issue) => issue.level === "warning")) return "warning";
  return "ready";
}

export const QueryActionPlanPreview: React.FC<QueryActionPlanPreviewProps> = ({ plan }) => {
  if (!plan || plan.actions.length === 0) return null;

  const severity = severityFor(plan);

  return (
    <div className={`query-action-plan-preview query-action-plan-preview--${severity} bg-card border border-border rounded-lg`}>
      <div className="query-action-plan-preview__header">
        <div className="query-action-plan-preview__title">
          <Sparkles size={14} className="query-action-plan-preview__sparkle" />
          <span>注解执行计划预览（SQL Action Plan）</span>
        </div>
        <span className={`query-action-plan-preview__status query-action-plan-preview__status--${severity}`}>
          {severity === "error" ? "校验失败" : severity === "warning" ? "警告" : "就绪"}
        </span>
      </div>

      <div className="query-action-plan-preview__actions">
        {plan.actions.map((action, index) => (
          <span key={index} className="query-action-plan-preview__action">
            <strong>@{action.type}</strong>
            <span className="query-action-plan-preview__action-label">({action.label})</span>
          </span>
        ))}
      </div>

      {plan.compiledSql !== plan.pureSql && (
        <div className="query-action-plan-preview__diff">
          <div className="query-action-plan-preview__diff-title">
            <FileCode size={12} />
            <span>SQL 编译重写对比（DSL Compile Rewrite）</span>
          </div>
          <div className="query-action-plan-preview__diff-content">
            <div className="query-action-plan-preview__diff-removed">- {plan.pureSql}</div>
            <div className="query-action-plan-preview__diff-added">+ {plan.compiledSql}</div>
          </div>
        </div>
      )}

      <div className="query-action-plan-preview__parameters">
        <div className="query-action-plan-preview__parameter">
          <Clock size={12} className="query-action-plan-preview__parameter-icon" />
          <span className="query-action-plan-preview__parameter-label">执行限时:</span>
          <span className="query-action-plan-preview__parameter-value">{plan.context.timeoutMs / 1000}s</span>
        </div>

        {plan.context.exportConfig?.enabled && (
          <div className="query-action-plan-preview__parameter">
            <Download size={12} className="query-action-plan-preview__parameter-icon query-action-plan-preview__parameter-icon--success" />
            <span className="query-action-plan-preview__parameter-label">导出格式:</span>
            <span className="query-action-plan-preview__parameter-value query-action-plan-preview__parameter-value--success">
              {plan.context.exportConfig.format.toUpperCase()}
            </span>
          </div>
        )}

        {plan.context.chartConfig?.enabled && (
          <div className="query-action-plan-preview__parameter">
            <BarChart3 size={12} className="query-action-plan-preview__parameter-icon query-action-plan-preview__parameter-icon--info" />
            <span className="query-action-plan-preview__parameter-label">渲染图表:</span>
            <span className="query-action-plan-preview__parameter-value query-action-plan-preview__parameter-value--info">
              {`${plan.context.chartConfig.type.toUpperCase()}(x=${plan.context.chartConfig.x || "自动"}, y=${plan.context.chartConfig.y || "自动"})`}
            </span>
          </div>
        )}
      </div>

      {plan.issues.length > 0 && (
        <div className="query-action-plan-preview__issues">
          {plan.issues.map((issue, index) => {
            const isError = issue.level === "error";
            const Icon = isError ? XCircle : AlertTriangle;
            return (
              <div
                key={index}
                className={`query-action-plan-preview__issue query-action-plan-preview__issue--${isError ? "error" : "warning"}`}
              >
                <Icon size={14} className="query-action-plan-preview__issue-icon" />
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
