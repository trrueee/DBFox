import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, FileWarning, RefreshCw, Trash2 } from "lucide-react";
import { diagnosticsApi, type DiagnosticLogsResponse } from "../lib/api/diagnostics";
import { getClientLogSource } from "../lib/diagnostics/clientLog";
import { getUserErrorMessage } from "../lib/api/client";

interface DiagnosticsPageProps {
  onToast: (msg: string, type?: "success" | "error" | "warning" | "info") => void;
}

export function DiagnosticsPage({ onToast }: DiagnosticsPageProps) {
  const [logs, setLogs] = useState<DiagnosticLogsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const existingSources = logs?.sources.filter((source) => source.exists).length ?? 0;

  return (
    <div className="hifi-diagnostics-page">
      <div className="hifi-page-header">
        <div>
          <h2>诊断日志</h2>
          <p>{logs?.generated_at ? formatDateTime(logs.generated_at) : "正在读取..."}</p>
        </div>
        <div className="hifi-diagnostics-actions">
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
        <Metric label="日志源" value={`${existingSources}/${logs?.sources.length ?? 0}`} />
        <Metric label="进程" value={String(logs?.environment.pid ?? "-")} />
        <Metric label="Python" value={String(logs?.environment.python ?? "-")} />
        <Metric label="模式" value={logs?.environment.frozen ? "分发版" : "开发版"} />
      </div>

      <div className="hifi-diagnostics-sources">
        {(logs?.sources ?? []).map((source) => (
          <section className="hifi-diagnostics-source" key={source.name}>
            <div className="hifi-diagnostics-source-header">
              <div>
                <h3>{source.name}</h3>
                <p>{source.path}</p>
              </div>
              <span className={source.exists ? "hifi-log-status ok" : "hifi-log-status missing"}>
                {source.exists ? `${formatBytes(source.size_bytes)}` : "未生成"}
              </span>
            </div>
            <pre>{source.content || (source.exists ? "无日志内容" : "日志文件不存在")}</pre>
          </section>
        ))}
        {!loading && logs?.sources.length === 0 ? (
          <div className="hifi-diagnostics-empty">
            <FileWarning size={18} />
            <span>暂无日志源</span>
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
  return {
    ...logs,
    sources: [...logs.sources, getClientLogSource()],
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

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
