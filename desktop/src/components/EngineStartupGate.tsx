import { useEffect, useState, type ReactNode } from "react";
import { FolderOpen, RefreshCw } from "lucide-react";
import { ApiError, waitEngineHealth, waitForEngineConfig } from "../lib/api/client";
import { FoxIcon } from "./brand/FoxIcon";
import { Button } from "./ui/button";

type StartupStage = "starting" | "health-check" | "failed" | "ready";

type StartupFailure = {
  code: string | null;
  summary: string;
};

function startupMessage(stage: StartupStage): string {
  switch (stage) {
    case "health-check":
      return "正在加载，请稍候…";
    case "failed":
      return "DBFox 暂时无法完成启动，请重试。";
    case "ready":
      return "加载完成。";
    default:
      return "正在加载，请稍候…";
  }
}

function startupFailure(error: unknown): StartupFailure {
  const code = error instanceof ApiError ? error.code ?? null : null;
  switch (code) {
    case "ENGINE_STARTUP_TIMEOUT":
      return { code, summary: "加载时间较长，请重试。" };
    case "ENGINE_HEALTH_UNAVAILABLE":
      return { code, summary: "DBFox 暂时无法完成启动，请重试。" };
    case "ENGINE_STOPPED":
      return { code, summary: "DBFox 已停止运行，请尝试重新启动。" };
    case "ENGINE_STARTUP_FAILED":
      return { code, summary: "DBFox 启动失败，请重试或查看诊断日志。" };
    case "ENGINE_RESTART_FAILED":
      return { code, summary: "DBFox 重新启动失败，请查看诊断日志。" };
    default:
      return { code, summary: "DBFox 暂时无法完成启动，请重试或查看诊断日志。" };
  }
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function invokeDesktopCommand(command: "restart_python_engine" | "open_diagnostic_logs") {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke(command);
}

export function EngineStartupGate({ children }: { children: ReactNode }) {
  const [stage, setStage] = useState<StartupStage>("starting");
  const [failure, setFailure] = useState<StartupFailure | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    void (async () => {
      try {
        await waitForEngineConfig({
          signal: controller.signal,
          onStatus(status) {
            if (!controller.signal.aborted && status.state === "starting") setStage("starting");
          },
        });
        if (controller.signal.aborted) return;
        setStage("health-check");
        await waitEngineHealth({ signal: controller.signal });
        if (!controller.signal.aborted) setStage("ready");
      } catch (error) {
        if (controller.signal.aborted) return;
        setFailure(startupFailure(error));
        setStage("failed");
      }
    })();

    return () => {
      controller.abort();
    };
  }, [attempt]);

  const retry = async () => {
    setStage("starting");
    setFailure(null);
    setActionMessage("正在重新加载 DBFox…");
    try {
      if (isTauriRuntime()) await invokeDesktopCommand("restart_python_engine");
      setAttempt((value) => value + 1);
    } catch {
      setFailure(startupFailure(new ApiError("Engine restart failed", 503, "ENGINE_RESTART_FAILED")));
      setActionMessage(null);
      setStage("failed");
    }
  };

  const openDiagnosticLogs = async () => {
    if (!isTauriRuntime()) {
      setActionMessage("诊断日志目录只能在 DBFox 桌面应用中打开。");
      return;
    }
    try {
      await invokeDesktopCommand("open_diagnostic_logs");
      setActionMessage("已打开诊断日志目录。");
    } catch {
      setActionMessage("无法打开诊断日志目录，请稍后重试。");
    }
  };

  if (stage === "ready") return <>{children}</>;

  const isLoading = stage !== "failed";

  return (
    <main className="engine-startup-gate" aria-live="polite" aria-busy={isLoading}>
      <span
        className={`engine-startup-gate__mark ${isLoading ? "is-loading" : "is-failed"}`}
        aria-hidden="true"
      >
        <FoxIcon variant="app" size={52} alt="" />
      </span>
      <h1>DBFox</h1>
      <p className="engine-startup-gate__message">
        {failure?.summary ?? startupMessage(stage)}
      </p>

      {stage === "failed" && (
        <>
          <div className="engine-startup-gate__actions">
            <Button type="button" onClick={() => void retry()}>
              <RefreshCw aria-hidden="true" />
              重试启动
            </Button>
            <Button type="button" variant="outline" onClick={() => void openDiagnosticLogs()}>
              <FolderOpen aria-hidden="true" />
              打开诊断日志
            </Button>
          </div>
          {failure?.code && (
            <details className="engine-startup-gate__details">
              <summary>技术信息</summary>
              <code className="engine-startup-gate__code">{failure.code}</code>
            </details>
          )}
        </>
      )}

      {actionMessage && <p className="engine-startup-gate__action-message" role="status">{actionMessage}</p>}
    </main>
  );
}
