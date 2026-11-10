import { useEffect, useRef, useState } from "react";
import { StopCircleIcon, TerminalWindowIcon } from "@/components/icons";
import { Button, EmptyState, LoadingState } from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";
import type { JobPage, JobView } from "../../lib/api/generated/types.gen";

type ReadPage = (after: number, tail: boolean, signal: AbortSignal) => Promise<JobPage>;

export function isActiveJob(job: JobView) {
  return job.state === "starting" || job.state === "running" || job.state === "stopping";
}

export function jobStatus(job: JobView) {
  switch (job.state) {
    case "starting": return "启动中";
    case "running":
      if (job.root_exit_code == null) return "运行中";
      return job.active_processes === 0 ? "正在收尾输出" : "等待子进程";
    case "stopping": return "停止中";
    case "exited": return job.root_exit_code === 0 ? "执行完成" : "执行失败";
    case "start_failed": return "启动失败";
    case "cancelled": return "已停止";
    case "timed_out": return "已超时";
    case "interrupted": return "已中断";
    case "unknown": return "结果未知";
  }
}

function programName(executable: string) {
  return executable.split(/[\\/]/).at(-1) || executable;
}

export function jobTitle(job: JobView) {
  return job.shell_script ?? (job.argv.join(" ") || programName(job.executable));
}

export function ExecutionLogView({ read, stop, onJobs }: {
  read: ReadPage;
  stop?: () => Promise<void>;
  onJobs?: () => void;
}) {
  const [page, setPage] = useState<JobPage | null>(null);
  const [history, setHistory] = useState<number[]>([]);
  const [error, setError] = useState("");
  const [stopError, setStopError] = useState("");
  const [stopRequested, setStopRequested] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const viewport = useRef<HTMLPreElement>(null);
  const follow = useRef(true);
  const historyCursor = history.at(-1);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cursor = historyCursor ?? 0;
    let initial = true;
    let chunks: JobPage["chunks"] = [];
    let expired = false;
    async function load() {
      try {
        const next = await read(cursor, initial && historyCursor === undefined, controller.signal);
        if (controller.signal.aborted) return;
        expired ||= next.cursor_expired;
        chunks = [...chunks, ...next.chunks.filter(chunk => chunk.cursor > cursor)]
          .filter(chunk => chunk.cursor >= next.job.first_cursor)
          .slice(-48);
        cursor = Math.max(cursor, next.next_cursor);
        setPage({ ...next, chunks, cursor_expired: expired });
        setError("");
        initial = false;
        if (historyCursor === undefined && (isActiveJob(next.job) || next.has_more)) {
          timer = setTimeout(load, next.has_more ? 80 : 650);
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(getUserErrorMessage(reason, "无法读取运行输出。"));
          if (historyCursor === undefined) timer = setTimeout(load, 2500);
        }
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [read, attempt, historyCursor]);

  useEffect(() => {
    if (historyCursor === undefined && follow.current && viewport.current) {
      viewport.current.scrollTop = viewport.current.scrollHeight;
    }
  }, [page, historyCursor]);

  if (!page) return error ? <div className="grid gap-2 p-4">
    <EmptyState title="无法载入执行记录" description={error} />
    <Button type="button" size="sm" variant="ghost" onClick={() => setAttempt(value => value + 1)}>重试</Button>
  </div> : <LoadingState label="正在读取运行输出" />;

  const { job } = page;
  const live = isActiveJob(job);
  const canBrowse = job.first_cursor < (page.chunks[0]?.cursor ?? job.last_cursor);
  return <section className="grid min-h-0 gap-3 p-4" aria-label="本机运行输出">
    <header className="flex min-w-0 items-center gap-2.5">
      <TerminalWindowIcon size={18} aria-hidden="true" className="shrink-0 text-[var(--agent-text-muted)]" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium" title={job.executable}>{programName(job.executable)}</div>
        <div className="text-xs text-[var(--agent-text-muted)]" role="status">
          {jobStatus(job)}{job.root_exit_code != null ? " · 退出码 " + job.root_exit_code : ""}
          {job.lifetime === "background" ? " · 后台" : ""}
        </div>
      </div>
      {onJobs ? <Button type="button" size="sm" variant="ghost" onClick={onJobs}>全部任务</Button> : null}
      {stop && live && historyCursor === undefined ? <Button type="button" size="sm" variant="ghost"
        disabled={stopRequested || job.state === "stopping" || Boolean(error)}
        onClick={() => {
          setStopRequested(true);
          setStopError("");
          void stop().catch(reason => {
            setStopRequested(false);
            setStopError(getUserErrorMessage(reason, "无法请求停止。"));
          });
        }}>
        <StopCircleIcon aria-hidden="true" />
        {stopRequested ? "已请求停止" : "停止"}
      </Button> : null}
    </header>
    <details className="min-w-0 text-xs text-[var(--agent-text-secondary)]">
      <summary className="cursor-pointer truncate">{jobTitle(job)}</summary>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 pt-2">
        <dt>程序</dt><dd className="m-0 break-all font-[var(--font-family-code)]">{job.executable}</dd>
        <dt>目录</dt><dd className="m-0 break-all font-[var(--font-family-code)]">{job.cwd}</dd>
        <dt>{job.shell_script ? "Shell 脚本" : "参数"}</dt>
        <dd className="m-0 whitespace-pre-wrap break-all font-[var(--font-family-code)]">{job.shell_script ?? JSON.stringify(job.argv.slice(1))}</dd>
        {job.reason ? <>
          <dt>原因</dt><dd className="m-0 break-all font-[var(--font-family-code)]">{job.reason}</dd>
        </> : null}
      </dl>
    </details>
    {error || stopError ? <p className="m-0 text-xs text-[var(--color-danger)]" role="alert">{error || stopError}</p> : null}
    {job.first_cursor > 1 || page.cursor_expired ? <p className="m-0 text-xs text-[var(--agent-text-muted)]">较早输出已超过保留范围。</p> : null}
    {!live && !job.output_finalized ? <p className="m-0 text-xs text-[var(--agent-text-muted)]">输出可能不完整。</p> : null}
    <pre ref={viewport} aria-label="命令日志" tabIndex={0}
      className="m-0 min-h-36 max-h-[min(58vh,32rem)] overflow-auto whitespace-pre-wrap break-all rounded-[var(--radius-card)] border border-[var(--agent-border)] bg-[var(--agent-surface-muted)] p-3 font-[var(--font-family-code)] text-xs leading-relaxed"
      onScroll={() => {
        if (viewport.current) {
          const { scrollHeight, scrollTop, clientHeight } = viewport.current;
          follow.current = scrollHeight - scrollTop - clientHeight < 32;
        }
      }}>
      {page.chunks.length === 0 ? <span className="text-[var(--agent-text-muted)]">{live ? "等待输出…" : "无保留输出"}</span> : page.chunks.map(chunk =>
        <span key={chunk.cursor} data-stream={chunk.stream}
          className={chunk.stream === "stderr" ? "text-[var(--agent-text-secondary)]" : undefined}>{chunk.text}</span>,
      )}
    </pre>
    <div className="flex flex-wrap items-center gap-1">
      {historyCursor === undefined ? canBrowse &&
        <Button type="button" variant="ghost" size="sm" onClick={() => setHistory([0])}>浏览历史输出</Button>
      : <>
        <Button type="button" variant="ghost" size="sm" disabled={history.length === 1}
          onClick={() => setHistory(values => values.slice(0, -1))}>上一页</Button>
        <Button type="button" variant="ghost" size="sm" disabled={!page.has_more || page.next_cursor <= historyCursor}
          onClick={() => setHistory(values => [...values, page.next_cursor])}>下一页</Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => {
          follow.current = true;
          setHistory([]);
        }}>回到最新</Button>
      </>}
    </div>
  </section>;
}
