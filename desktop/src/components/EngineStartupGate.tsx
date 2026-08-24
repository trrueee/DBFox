import { useEffect, useRef, useState, type ReactNode } from "react";
import { FolderOpen, RefreshCw } from "lucide-react";
import {
  ApiError,
  getRuntimeSession,
  subscribeEngineState,
  waitEngineHealth,
  waitForEngineConfig,
} from "../lib/api/client";
import {
  isEngineDesktopHost,
  openDesktopDiagnosticLogs,
  restartDesktopEngine,
} from "../lib/desktopHost";
import { FoxIcon } from "./brand/FoxIcon";
import { Button } from "./ui/button";

type StartupStage = "starting" | "health-check" | "failed" | "ready";

type StartupFailure = {
  code: string | null;
  summary: string;
  fingerprint?: string | null;
  engineStage?: string | null;
};

function startupMessage(stage: StartupStage, enginePhase: string | null): string {
  if (stage === "starting") {
    if (enginePhase === "recovering") return "正在恢复工作区，请稍候…";
    if (enginePhase === "migrating" || enginePhase === "maintaining") {
      return "正在准备 DBFox，请稍候…";
    }
    return "正在启动 DBFox…";
  }
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
  const detail = error instanceof ApiError && isStartupFailureDetail(error.detail)
    ? error.detail
    : null;
  const diagnostics = {
    fingerprint: detail?.fingerprint ?? null,
    engineStage: detail?.stage ?? null,
  };
  switch (code) {
    case "DBFOX_METADATA_FOREIGN_KEY_VIOLATION":
      return {
        code,
        summary: "本地数据库完整性检查失败，请查看诊断日志。",
        ...diagnostics,
      };
    case "DBFOX_METADATA_MIGRATION_FAILED":
      return {
        code,
        summary: "本地数据库升级失败，请查看诊断日志。",
        ...diagnostics,
      };
    case "ENGINE_STARTUP_TIMEOUT":
      return { code, summary: "加载时间较长，请重试。" };
    case "ENGINE_HEALTH_UNAVAILABLE":
      return { code, summary: "DBFox 暂时无法完成启动，请重试。" };
    case "ENGINE_STOPPED":
      return { code, summary: "DBFox 已停止运行，请尝试重新启动。" };
    case "ENGINE_STARTUP_FAILED":
      return { code, summary: "DBFox 启动失败，请重试或查看诊断日志。", ...diagnostics };
    case "ENGINE_RESTART_FAILED":
      return { code, summary: "DBFox 重新启动失败，请查看诊断日志。" };
    default:
      return { code, summary: "DBFox 暂时无法完成启动，请重试或查看诊断日志。" };
  }
}

function isStartupFailureDetail(
  value: unknown,
): value is { fingerprint: string; stage: string | null } {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.fingerprint === "string"
    && (typeof candidate.stage === "string" || candidate.stage === null);
}

export function EngineStartupGate({ children }: { children: ReactNode }) {
  const [stage, setStage] = useState<StartupStage>("starting");
  const [failure, setFailure] = useState<StartupFailure | null>(null);
  const [enginePhase, setEnginePhase] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [runtimeNotice, setRuntimeNotice] = useState<string | null>(null);
  const generationRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();

    void (async () => {
      try {
        await waitForEngineConfig({
          signal: controller.signal,
          onStatus(status) {
            if (!controller.signal.aborted && status.state === "starting") {
              setEnginePhase(status.stage ?? null);
              setStage("starting");
            }
          },
        });
        if (controller.signal.aborted) return;
        setStage("health-check");
        await waitEngineHealth({ signal: controller.signal });
        if (!controller.signal.aborted) {
          generationRef.current = getRuntimeSession().generation;
          setStage("ready");
        }
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

  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    void subscribeEngineState((status) => {
      if (disposed) return;
      if (status.state === "restarting") {
        setRuntimeNotice("本地引擎意外退出，正在自动恢复…");
        return;
      }
      if (status.state === "failed") {
        setRuntimeNotice(null);
        setFailure(startupFailure(new ApiError(
          status.error || "Engine restart failed",
          503,
          status.failure?.code || "ENGINE_RESTART_FAILED",
          [],
          status.failure ? { ...status.failure, stage: status.stage ?? null } : undefined,
        )));
        setStage("failed");
        return;
      }
      if (status.state !== "ready" || (status.generation ?? 0) <= generationRef.current) return;
      const previousGeneration = generationRef.current;
      void (async () => {
        try {
          await waitForEngineConfig({ afterGeneration: previousGeneration, attempts: 40, intervalMs: 250 });
          await waitEngineHealth({ attempts: 20, intervalMs: 250 });
          if (!disposed) {
            generationRef.current = getRuntimeSession().generation;
            setRuntimeNotice(null);
            setFailure(null);
            setStage("ready");
          }
        } catch (error) {
          if (!disposed) {
            setRuntimeNotice(null);
            setFailure(startupFailure(error));
            setStage("failed");
          }
        }
      })();
    }).then((cleanup) => {
      if (disposed) cleanup();
      else unsubscribe = cleanup;
    });
    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }, []);

  const retry = async () => {
    setStage("starting");
    setFailure(null);
    setEnginePhase(null);
    setActionMessage("正在重新加载 DBFox…");
    try {
      if (isEngineDesktopHost()) await restartDesktopEngine();
      setAttempt((value) => value + 1);
    } catch {
      setFailure(startupFailure(new ApiError("Engine restart failed", 503, "ENGINE_RESTART_FAILED")));
      setActionMessage(null);
      setStage("failed");
    }
  };

  const openDiagnosticLogs = async () => {
    if (!isEngineDesktopHost()) {
      setActionMessage("诊断日志目录只能在 DBFox 桌面应用中打开。");
      return;
    }
    try {
      await openDesktopDiagnosticLogs();
      setActionMessage("已打开诊断日志目录。");
    } catch {
      setActionMessage("无法打开诊断日志目录，请稍后重试。");
    }
  };

  if (stage === "ready") {
    return (
      <>
        {runtimeNotice ? <div className="engine-runtime-notice" role="status">{runtimeNotice}</div> : null}
        {children}
      </>
    );
  }

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
        {failure?.summary ?? startupMessage(stage, enginePhase)}
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
              <code className="engine-startup-gate__code">
                {failure.code}
                {failure.engineStage ? ` · ${failure.engineStage}` : ""}
                {failure.fingerprint ? ` · ${failure.fingerprint}` : ""}
              </code>
            </details>
          )}
        </>
      )}

      {actionMessage && <p className="engine-startup-gate__action-message" role="status">{actionMessage}</p>}
    </main>
  );
}
