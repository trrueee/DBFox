import {
  CheckCircle2,
  ChevronDown,
  Circle,
  Clock3,
  Loader2,
  ListChecks,
  ShieldAlert,
  Table2,
  Wrench,
  XCircle,
} from "lucide-react";
import * as Collapsible from "@radix-ui/react-collapsible";
import { useState } from "react";
import type { ConversationActivity } from "../../../types/conversation";

export function ActivityFeed({
  activities,
  onSelectArtifact,
}: {
  activities: ConversationActivity[];
  onSelectArtifact?: (artifactId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  if (activities.length === 0) {
    return <div className="conv-activity-current" role="status">正在准备分析…</div>;
  }
  const current = activities.findLast((item) => ["running", "waiting", "pending"].includes(item.status))
    || activities.at(-1)!;
  const completedCount = activities.filter((item) => item.status === "completed").length;
  return (
    <Collapsible.Root asChild open={expanded} onOpenChange={setExpanded}>
      <section className="conv-activity-feed" aria-label="分析过程">
        <Collapsible.Trigger asChild>
          <button type="button" className={`conv-activity-current is-${current.status}`}>
            {activityIcon(current)}
            <span>
              <strong>{current.title}</strong>
              {current.summary && <small>{current.summary}</small>}
            </span>
            <em aria-label={`${completedCount} 个步骤已完成`}>{completedCount}/{activities.length}</em>
            <ChevronDown size={14} aria-hidden="true" />
          </button>
        </Collapsible.Trigger>
        <Collapsible.Content asChild>
          <ol className="conv-activity-list">
          {activities.map((activity) => (
            <li key={activity.id} className={`is-${activity.status}`}>
              <span className="conv-activity-node">{activityIcon(activity)}</span>
              <div className="conv-activity-content">
                <div className="conv-activity-title-row">
                  <strong>{activity.title}</strong>
                  {activityDuration(activity) && (
                    <time>
                      <Clock3 size={12} aria-hidden="true" />
                      {activityDuration(activity)}
                    </time>
                  )}
                </div>
                {activity.summary && <small>{activity.summary}</small>}
                {activity.kind === "plan" && Boolean(activity.steps?.length) && (
                  <ol className="conv-activity-plan" aria-label="分析计划步骤">
                    {activity.steps?.map((step) => (
                      <li key={step.id} className={`is-${step.status}`}>
                        {step.status === "completed" ? (
                          <CheckCircle2 size={13} aria-hidden="true" />
                        ) : step.status === "in_progress" ? (
                          <Loader2 className="is-spinning" size={13} aria-hidden="true" />
                        ) : step.status === "blocked" ? (
                          <ShieldAlert size={13} aria-hidden="true" />
                        ) : (
                          <Circle size={13} aria-hidden="true" />
                        )}
                        <span>
                          <strong>{step.title}</strong>
                          {step.note && <small>{step.note}</small>}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
                {Boolean(activity.artifact_ids?.length) && (
                  <div className="conv-activity-artifacts" aria-label="关联工件">
                    {activity.artifact_ids?.map((artifactId, index) => (
                      <button key={artifactId} type="button" onClick={() => onSelectArtifact?.(artifactId)}>
                        <Table2 size={12} aria-hidden="true" />
                        结果 {index + 1}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </li>
          ))}
          </ol>
        </Collapsible.Content>
      </section>
    </Collapsible.Root>
  );
}

function activityDuration(activity: ConversationActivity): string | null {
  if (!activity.started_at || !activity.completed_at) return null;
  const start = new Date(activity.started_at).getTime();
  const end = new Date(activity.completed_at).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  const milliseconds = end - start;
  return milliseconds < 1_000 ? `${milliseconds}ms` : `${(milliseconds / 1_000).toFixed(1)}s`;
}

function activityIcon(activity: ConversationActivity) {
  if (activity.status === "running") return <Loader2 className="is-spinning" size={15} aria-hidden="true" />;
  if (activity.status === "completed") return <CheckCircle2 size={15} aria-hidden="true" />;
  if (activity.status === "failed" || activity.status === "cancelled") {
    return <XCircle size={15} aria-hidden="true" />;
  }
  if (activity.status === "waiting") return <ShieldAlert size={15} aria-hidden="true" />;
  if (activity.kind === "repair") return <Wrench size={15} aria-hidden="true" />;
  if (activity.kind === "plan") return <ListChecks size={15} aria-hidden="true" />;
  return <Circle size={15} aria-hidden="true" />;
}
