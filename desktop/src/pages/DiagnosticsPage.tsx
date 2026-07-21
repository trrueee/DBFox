import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Check, CheckCircle2, ChevronDown, Copy, FileText, FileWarning, RefreshCw, Trash2 } from "lucide-react";
import { Button, EmptyState, ErrorState } from "../components/ui";
import { DangerConfirmDialog, type ConfirmationDetails } from "../components/DangerConfirmDialog";
import { SettingsSection, SettingsToggle } from "../components/settings";
import { diagnosticsApi, type DiagnosticLogSource, type DiagnosticLogsResponse } from "../lib/api/diagnostics";
import { getClientLogSource } from "../lib/diagnostics/clientLog";
import { getUserErrorMessage } from "../lib/api/client";
import "./DiagnosticsPage.css";

interface DiagnosticsPageProps {
  onToast: (msg: string, type?: "success" | "error" | "warning" | "info") => void;
  chrome?: "page" | "workspace";
}

type DiagnosticGroupKey = "backend" | "frontend";

interface DiagnosticLogGroup {
  key: DiagnosticGroupKey;
  label: string;
  sources: DiagnosticLogSource[];
  sourceNames: string[];
  exists: boolean;
  sizeBytes: number;
  modifiedAt: string | null;
  content: string;
}

export function DiagnosticsPage({ onToast, chrome = "page" }: DiagnosticsPageProps) {
  const [logs, setLogs] = useState<DiagnosticLogsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showEmptyLogs, setShowEmptyLogs] = useState(false);
  const [selectedGroupKey, setSelectedGroupKey] = useState<DiagnosticGroupKey>("backend");
  const [groupMenuOpen, setGroupMenuOpen] = useState(false);
  const [auditConfirmation, setAuditConfirmation] = useState<ConfirmationDetails | null>(null);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLogs(await loadDiagnosticLogs());
    } catch (err) {
      const message = getUserErrorMessage(err, "诊断日志加载失败");
      setError(message);
      setLogs(frontendOnlyLogs());
      onToast(message, "error");
    } finally {
      setLoading(false);
    }
  }, [onToast]);

  useEffect(() => {
    let cancelled = false;

    async function loadInitialLogs() {
      setLoading(true);
      setError(null);
      try {
        const nextLogs = await loadDiagnosticLogs();
        if (!cancelled) setLogs(nextLogs);
      } catch (err) {
        if (cancelled) return;
        const message = getUserErrorMessage(err, "诊断日志加载失败");
        setError(message);
        setLogs(frontendOnlyLogs());
        onToast(message, "error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadInitialLogs();
    return () => { cancelled = true; };
  }, [onToast]);

  const bundleText = useMemo(() => {
    if (!logs) return "";
    return JSON.stringify(logs, null, 2);
  }, [logs]);

  const handleCopy = async () => {
    if (!bundleText) return;
    try {
      await navigator.clipboard.writeText(bundleText);
      onToast("诊断包已复制", "success");
    } catch {
      onToast("复制失败", "error");
    }
  };

  const handleClearLogs = async () => {
    try {
      const result = await diagnosticsApi.clearLogs();
      if (result.cleared) {
        onToast(`已清空 ${result.sources_cleared.length} 个日志源`, "success");
      } else {
        onToast("没有可清空的日志文件", "warning");
      }
      await loadLogs();
    } catch (err) {
      onToast(getUserErrorMessage(err, "清空日志失败"), "error");
    }
  };

  const requestAuditClear = () => {
    setAuditConfirmation({
      confirm_token: "security-audit-clear",
      impact_summary: "这会删除本机现有的安全审计记录。系统会保留一条本次清理操作的审计记录。此操作不会删除诊断日志、对话或工件。",
      expected_confirm_text: "清空安全审计",
      onCancel: () => setAuditConfirmation(null),
      onConfirm: async (confirmText) => {
        const result = await diagnosticsApi.clearSecurityAudit(confirmText);
        setAuditConfirmation(null);
        onToast(`已清理 ${result.records_deleted} 条安全审计记录`, "success");
        await loadLogs();
      },
    });
  };

  const visibleGroups = useMemo(() => {
    if (!logs) return [];
    return buildDiagnosticGroups(logs.sources, showEmptyLogs);
  }, [logs, showEmptyLogs]);

  const resolvedSelectedGroupKey = visibleGroups.some((group) => group.key === selectedGroupKey)
    ? selectedGroupKey
    : visibleGroups[0]?.key ?? selectedGroupKey;
  const selectedGroup = visibleGroups.find((group) => group.key === resolvedSelectedGroupKey) || visibleGroups[0] || null;
  const totalSourcesCount = logs?.sources.length ?? 0;
  const nonEmptySourcesCount = logs?.sources.filter((source) => source.exists && source.size_bytes > 0).length ?? 0;
  const generatedAtLabel = logs?.generated_at ? formatDateTime(logs.generated_at) : "正在读取…";
  const actions = (
    <div className="diagnostics-actions">
      <SettingsToggle
        checked={showEmptyLogs}
        onCheckedChange={setShowEmptyLogs}
        label="显示空日志"
        compact
      />
      <span className="diagnostics-badge">
        <CheckCircle2 size={14} />
        已脱敏
      </span>
      <Button type="button" variant="outline" size="sm" onClick={loadLogs} disabled={loading}>
        <RefreshCw size={14} />
        刷新
      </Button>
      <Button type="button" variant="outline" size="sm" onClick={handleClearLogs} disabled={loading}>
        <Trash2 size={14} />
        清空日志
      </Button>
      <Button type="button" variant="outline" size="sm" onClick={requestAuditClear} disabled={loading}>
        <Trash2 size={14} />
        清空审计
      </Button>
      <Button type="button" size="sm" onClick={handleCopy} disabled={!logs}>
        <Copy size={14} />
        复制诊断包
      </Button>
    </div>
  );

  return (
    <div className={`diagnostics-page${chrome === "workspace" ? " diagnostics-page--workspace" : ""}`}>
      {chrome === "workspace" ? (
        <div className="diagnostics-page-toolbar">
          <span className="diagnostics-page-subtitle">{generatedAtLabel}</span>
          {actions}
        </div>
      ) : (
        <div className="diagnostics-page-header">
          <div>
            <h2 className="diagnostics-page-title">诊断日志</h2>
            <p className="diagnostics-page-subtitle">{generatedAtLabel}</p>
          </div>
          {actions}
        </div>
      )}

      {error ? (
        <ErrorState className="diagnostics-error" title="诊断日志加载失败" description={error} />
      ) : null}

      <div className="diagnostics-content">
        <SettingsSection
          icon={Activity}
          title="运行环境"
          description="用于判断问题发生在引擎、桌面端还是当前运行环境。"
        >
          <div className="diagnostics-summary">
            <Metric label="日志源" value={`${nonEmptySourcesCount}/${totalSourcesCount} 有内容`} />
            <Metric label="日志分组" value={`${visibleGroups.length}/2 可查看`} />
            <Metric label="进程" value={String(logs?.environment.pid ?? "-")} />
            <Metric label="Python" value={String(logs?.environment.python ?? "-")} />
            <Metric label="模式" value={logs?.environment.frozen ? "分发版" : "开发版"} />
            <Metric label="安全审计" value={`${logs?.security_audit.records.length ?? 0} 条（近 ${logs?.security_audit.export_window_days ?? 7} 天）`} />
          </div>
        </SettingsSection>

        <SettingsSection
          icon={FileText}
          title="日志内容"
          description="日志已按前端和后端分组，并在生成诊断包前完成脱敏。"
          className="diagnostics-log-section"
          trailing={<span className="diagnostics-source-count">{selectedGroup ? `${selectedGroup.sourceNames.length} 个原始源` : "无日志源"}</span>}
        >
          {visibleGroups.length > 0 ? (
            <div className="diagnostics-source-toolbar">
              <div className="diagnostics-source-picker">
                <span>日志分组</span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="diagnostics-source-trigger"
                  aria-label="日志分组"
                  aria-haspopup="listbox"
                  aria-expanded={groupMenuOpen}
                  onClick={() => setGroupMenuOpen((value) => !value)}
                >
                  <span>{selectedGroup?.label || "选择日志"}</span>
                  <ChevronDown size={14} />
                </Button>
                {groupMenuOpen ? (
                  <div className="diagnostics-source-menu" role="listbox" aria-label="日志分组">
                    {visibleGroups.map((group) => (
                      <Button
                        key={group.key}
                        type="button"
                        variant="ghost"
                        role="option"
                        aria-selected={group.key === resolvedSelectedGroupKey}
                        className={`diagnostics-source-option${group.key === resolvedSelectedGroupKey ? " is-active" : ""}`}
                        onClick={() => {
                          setSelectedGroupKey(group.key);
                          setGroupMenuOpen(false);
                        }}
                      >
                        <span>
                          <strong>{group.label}</strong>
                          <small>{group.sourceNames.join(", ") || "无原始源"}</small>
                        </span>
                        <em>{formatBytes(group.sizeBytes)}</em>
                        {group.key === resolvedSelectedGroupKey ? <Check size={14} /> : null}
                      </Button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="diagnostics-sources">
            {selectedGroup ? (
              <section className="diagnostics-source" key={selectedGroup.key}>
                <div className="diagnostics-source-header">
                  <div>
                    <h4>{selectedGroup.label}</h4>
                    <p>{selectedGroup.sourceNames.join(", ")}</p>
                  </div>
                  <span
                    className={
                      selectedGroup.exists
                        ? "diagnostics-log-status diagnostics-log-status--ok"
                        : "diagnostics-log-status diagnostics-log-status--missing"
                    }
                  >
                    {selectedGroup.exists ? `${formatBytes(selectedGroup.sizeBytes)}` : "未生成"}
                  </span>
                </div>
                <pre className="diagnostics-source-content">
                  {selectedGroup.content || (selectedGroup.exists ? "无日志内容" : "日志文件不存在")}
                </pre>
              </section>
            ) : null}
            {!loading && visibleGroups.length === 0 ? (
              <EmptyState
                className="diagnostics-empty"
                icon={<FileWarning size={18} />}
                title="暂无有效日志（包含内容的日志源）"
              />
            ) : null}
          </div>
        </SettingsSection>
      </div>
      <DangerConfirmDialog details={auditConfirmation} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="diagnostics-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

async function loadDiagnosticLogs(): Promise<DiagnosticLogsResponse> {
  return withClientLogs(await diagnosticsApi.getLogs());
}

function withClientLogs(logs: DiagnosticLogsResponse): DiagnosticLogsResponse {
  const clientSource = getClientLogSource();
  return {
    ...logs,
    sources: logs.sources.some((source) => source.name === clientSource.name)
      ? logs.sources
      : [...logs.sources, clientSource],
  };
}

function frontendOnlyLogs(): DiagnosticLogsResponse {
  return {
    generated_at: new Date().toISOString(),
    policy: {
      redacted: true,
      max_lines_per_source: 300,
      omitted: ["backend logs unavailable"],
    },
    environment: {
      app: "DBFox",
      frontend_only: true,
    },
    sources: [getClientLogSource()],
    security_audit: {
      retention_days: 90,
      export_window_days: 7,
      max_records: 500,
      records: [],
    },
  };
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function buildDiagnosticGroups(sources: DiagnosticLogSource[], showEmpty: boolean): DiagnosticLogGroup[] {
  const groups: Record<DiagnosticGroupKey, DiagnosticLogGroup> = {
    backend: emptyLogGroup("backend", "后端日志"),
    frontend: emptyLogGroup("frontend", "前端日志"),
  };

  for (const source of sources) {
    groups[diagnosticGroupKey(source)].sources.push(source);
  }

  return (["backend", "frontend"] as const)
    .map((key) => finalizeLogGroup(groups[key], showEmpty))
    .filter((group) => showEmpty || group.sources.some((source) => source.exists && source.size_bytes > 0));
}

function emptyLogGroup(key: DiagnosticGroupKey, label: string): DiagnosticLogGroup {
  return {
    key,
    label,
    sources: [],
    sourceNames: [],
    exists: false,
    sizeBytes: 0,
    modifiedAt: null,
    content: "",
  };
}

function diagnosticGroupKey(source: DiagnosticLogSource): DiagnosticGroupKey {
  const name = source.name.toLowerCase();
  const path = source.path.toLowerCase();
  if (name.startsWith("frontend") || name.includes("client") || path.startsWith("localstorage:")) {
    return "frontend";
  }
  return "backend";
}

function finalizeLogGroup(group: DiagnosticLogGroup, showEmpty: boolean): DiagnosticLogGroup {
  const contentSources = showEmpty ? group.sources : group.sources.filter((source) => source.exists && source.size_bytes > 0);
  return {
    ...group,
    sourceNames: group.sources.map((source) => source.name),
    exists: group.sources.some((source) => source.exists),
    sizeBytes: group.sources.reduce((total, source) => total + source.size_bytes, 0),
    modifiedAt: latestModifiedAt(group.sources),
    content: contentSources.map(formatGroupedSourceContent).filter(Boolean).join("\n\n"),
  };
}

function formatGroupedSourceContent(source: DiagnosticLogSource): string {
  const state = source.exists ? formatBytes(source.size_bytes) : "missing";
  const header = `--- ${source.name} | ${state} | ${source.path} ---`;
  const body = source.content || (source.exists ? "无日志内容" : "日志文件不存在");
  return `${header}\n${body}`;
}

function latestModifiedAt(sources: DiagnosticLogSource[]): string | null {
  return sources
    .map((source) => source.modified_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) || null;
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
