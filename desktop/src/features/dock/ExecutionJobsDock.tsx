import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRightIcon, TerminalWindowIcon } from "@/components/icons";
import { Button, EmptyState, LoadingState } from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";
import { localExecutionApi } from "../../lib/api/localExecution";
import { openExecutionDock } from "../../stores/executionDock";
import { ExecutionLogView, isActiveJob, jobStatus, jobTitle } from "./ExecutionLogView";

export function ExecutionJobsDock({ conversationId, jobId }: { conversationId: string; jobId?: string }) {
  return jobId ? <LiveJob key={jobId} conversationId={conversationId} jobId={jobId} />
    : <JobList conversationId={conversationId} />;
}

function LiveJob({ conversationId, jobId }: { conversationId: string; jobId: string }) {
  const read = useCallback((after: number, tail: boolean, signal: AbortSignal) =>
    localExecutionApi.read(conversationId, jobId, after, tail, signal), [conversationId, jobId]);
  return <ExecutionLogView read={read}
    stop={() => localExecutionApi.stop(conversationId, jobId)}
    onJobs={() => openExecutionDock(conversationId)} />;
}

function JobList({ conversationId }: { conversationId: string }) {
  const jobs = useQuery({
    queryKey: ["execution-jobs", conversationId],
    queryFn: ({ signal }) => localExecutionApi.list(conversationId, signal),
    refetchInterval: query => query.state.data?.some(isActiveJob) ? 1200 : false,
    gcTime: 0,
    retry: false,
  });
  if (jobs.isPending) return <LoadingState label="正在读取本机任务" />;
  if (jobs.isError) return <div className="grid gap-2 p-4">
    <EmptyState title="无法载入本机任务" description={getUserErrorMessage(jobs.error, "请重试读取。")} />
    <Button type="button" size="sm" variant="ghost" onClick={() => void jobs.refetch()}>重试</Button>
  </div>;
  if (!jobs.data.length) return <EmptyState title="暂无本机任务" />;
  return <ul className="m-0 grid list-none gap-1 p-3" aria-label="本机任务">
    {jobs.data.map(job => <li key={job.id} className="min-w-0">
      <button type="button"
        className="flex w-full min-w-0 items-center gap-2.5 rounded-[var(--radius-row)] p-2 text-left hover:bg-[var(--control-bg-hover)] focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
        onClick={() => openExecutionDock(conversationId, job.id)}>
        <TerminalWindowIcon size={18} className="shrink-0 text-[var(--agent-text-muted)]" aria-hidden="true" />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-sm">{jobTitle(job)}</span>
          <span className="text-xs text-[var(--agent-text-muted)]">{jobStatus(job)}</span>
        </span>
        <ArrowUpRightIcon size={14} className="shrink-0 text-[var(--agent-text-muted)]" aria-hidden="true" />
      </button>
    </li>)}
  </ul>;
}
