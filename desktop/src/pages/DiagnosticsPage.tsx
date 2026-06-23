import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, CheckCircle2, ChevronDown, Copy, FileWarning, RefreshCw, Trash2 } from "lucide-react";
import { diagnosticsApi, type DiagnosticLogSource, type DiagnosticLogsResponse } from "../lib/api/diagnostics";
import { getClientLogSource } from "../lib/diagnostics/clientLog";
import { getUserErrorMessage } from "../lib/api/client";

interface DiagnosticsPageProps {
  onToast: (msg: string, type?: "success" | "error" | "warning" | "info") => void;
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

export function DiagnosticsPage({ onToast }: DiagnosticsPageProps) {
  const [logs, setLogs] = useState<DiagnosticLogsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showEmptyLogs, setShowEmptyLogs] = useState(false);
  const [selectedGroupKey, setSelectedGroupKey] = useState<DiagnosticGroupKey>("backend");
  const [groupMenuOpen, setGroupMenuOpen] = useState(false);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLogs(withClientLogs(await diagnosticsApi.getLogs()));
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
    void loadLogs();
  }, [loadLogs]);

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

  const visibleGroups = useMemo(() => {
    if (!logs) return [];
    return buildDiagnosticGroups(logs.sources, showEmptyLogs);
  }, [logs, showEmptyLogs]);

  useEffect(() => {
    if (visibleGroups.length === 0) return;
    if (!visibleGroups.some((group) => group.key === selectedGroupKey)) {
      setSelectedGroupKey(visibleGroups[0].key);
    }
  }, [selectedGroupKey, visibleGroups]);

  const selectedGroup = visibleGroups.find((group) => group.key === selectedGroupKey) || visibleGroups[0] || null;
  const totalSourcesCount = logs?.sources.length ?? 0;
  const nonEmptySourcesCount = logs?.sources.filter((source) => source.exists && source.size_bytes > 0).length ?? 0;

  return (
    <div className="hifi-diagnostics-page">
      <div className="hifi-page-header">
        <div>
          <h2>诊断日志</h2>
          <p>{logs?.generated_at ? formatDateTime(logs.generated_at) : "正在读取..."}</p>
        </div>
        <div className="hifi-diagnostics-actions">
          <label className="hifi-diagnostics-toggle-label">
            <input
              type="checkbox"
              checked={showEmptyLogs}
              aria-label="显示空日志"
              onChange={(e) => setShowEmptyLogs(e.target.checked)}
            />
            <span>显示空日志</span>
          </label>
          <span className="hifi-diagnostics-badge">
            <CheckCircle2 size={14} />
            已脱敏
          </span>
          <button className="hifi-btn" type="button" onClick={loadLogs} disabled={loading}>
            <RefreshCw size={14} />
            刷新
          </button>
          <button className="hifi-btn hifi-btn-outline" type="button" onClick={handleClearLogs} disabled={loading}>
            <Trash2 size={14} />
            清空
          </button>
          <button className="hifi-btn hifi-btn-primary" type="button" onClick={handleCopy} disabled={!logs}>
            <Copy size={14} />
            复制诊断包
          </button>
        </div>
      </div>

      {error ? (
        <div className="hifi-diagnostics-error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      ) : null}

      <div className="hifi-diagnostics-summary">
        <Metric label="日志源" value={`${nonEmptySourcesCount}/${totalSourcesCount} 有内容`} />
        <Metric label="日志分组" value={`${visibleGroups.length}/2 可查看`} />
        <Metric label="进程" value={String(logs?.environment.pid ?? "-")} />
        <Metric label="Python" value={String(logs?.environment.python ?? "-")} />
        <Metric label="模式" value={logs?.environment.frozen ? "分发版" : "开发版"} />
      </div>

      {visibleGroups.length > 0 ? (
        <div className="hifi-diagnostics-source-toolbar">
          <div className="hifi-diagnostics-source-picker">
            <span>日志分组</span>
            <button
              type="button"
              className="hifi-diagnostics-source-trigger"
              aria-label="日志分组"
              aria-haspopup="listbox"
              aria-expanded={groupMenuOpen}
              onClick={() => setGroupMenuOpen((value) => !value)}
            >
              <span>{selectedGroup?.label || "选择日志"}</span>
              <ChevronDown size={14} />
            </button>
            {groupMenuOpen ? (
              <div className="hifi-diagnostics-source-menu" role="listbox" aria-label="日志分组">
                {visibleGroups.map((group) => (
                  <button
                    key={group.key}
                    type="button"
                    role="option"
                    aria-selected={group.key === selectedGroupKey}
                    className={`hifi-diagnostics-source-option ${group.key === selectedGroupKey ? "active" : ""}`}
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
                    {group.key === selectedGroupKey ? <Check size={14} /> : null}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <span className="hifi-diagnostics-source-count">
            {selectedGroup ? `${selectedGroup.sourceNames.length} 个原始源` : "无日志源"}
          </span>
        </div>
      ) : null}

      <div className="hifi-diagnostics-sources">
        {selectedGroup ? (
          <section className="hifi-diagnostics-source" key={selectedGroup.key}>
            <div className="hifi-diagnostics-source-header">
              <div>
                <h3>{selectedGroup.label}</h3>
                <p>{selectedGroup.sourceNames.join(", ")}</p>
              </div>
              <span className={selectedGroup.exists ? "hifi-log-status ok" : "hifi-log-status missing"}>
                {selectedGroup.exists ? `${formatBytes(selectedGroup.sizeBytes)}` : "未生成"}
              </span>
            </div>
            <pre>{selectedGroup.content || (selectedGroup.exists ? "无日志内容" : "日志文件不存在")}</pre>
          </section>
        ) : null}
        {!loading && visibleGroups.length === 0 ? (
          <div className="hifi-diagnostics-empty">
            <FileWarning size={18} />
            <span>暂无有效日志（包含内容的日志源）</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="hifi-diagnostics-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
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
