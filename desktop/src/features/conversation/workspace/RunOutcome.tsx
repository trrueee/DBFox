/*
 * Terminal Run feedback composes DBFox's vendored shadcn/ui Alert:
 * https://ui.shadcn.com/docs/components/base/alert
 *
 * One line of outcome, one line of cause, and a way back into the work.
 * Step progress lives in the plan card — it is not repeated here.
 */
import { AlertTriangle, CircleStop, FileOutput } from "lucide-react";

import type {
  AssistantMessageItem,
  ConversationArtifact,
  ConversationRun,
} from "../../../types/conversation";
import { getUserErrorMessage } from "../../../lib/api/client";
import { completionLimitationLabel } from "../../../lib/presentation";
import { Alert, AlertDescription, AlertTitle, Button } from "../../../components/ui";

interface RunOutcomeProps {
  run: ConversationRun;
  finalAnswer?: AssistantMessageItem;
  artifacts: readonly ConversationArtifact[];
  onSelectArtifact?: (artifactId: string) => void;
}

export function RunOutcome({
  run,
  finalAnswer,
  artifacts,
  onSelectArtifact,
}: RunOutcomeProps) {
  const outcome = run.error || run.status === "failed"
    ? "failed"
    : finalAnswer?.payload.completion_disposition === "bounded_partial"
      ? "partial"
      : run.status === "cancelled"
        ? "cancelled"
        : null;
  if (!outcome) return null;

  const preservedArtifacts = artifacts.filter(
    (artifact) => artifact.visibility === "primary" && artifact.status === "completed",
  );
  const firstArtifact = preservedArtifacts[0];
  const limitation = finalAnswer?.payload.limitation_codes
    .map(completionLimitationLabel)
    .join("；");

  return (
    <Alert
      variant={outcome === "failed" ? "destructive" : "default"}
      role={outcome === "failed" ? "alert" : "status"}
      className="conv-run-alert conv-run-outcome"
      data-outcome={outcome}
    >
      {outcome === "cancelled"
        ? <CircleStop aria-hidden="true" />
        : <AlertTriangle aria-hidden="true" />}
      <AlertTitle>{outcomeTitle(outcome, preservedArtifacts.length)}</AlertTitle>
      <AlertDescription>
        {outcome === "failed" ? (
          <p>{getUserErrorMessage(run.error?.message, "本次任务未完成。")}</p>
        ) : limitation ? (
          <p>停止原因：{limitation}。</p>
        ) : null}

        {firstArtifact && onSelectArtifact ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="conv-run-outcome__artifact"
            onClick={() => onSelectArtifact(firstArtifact.id)}
            aria-label={`打开已保留工件：${firstArtifact.title}`}
          >
            <FileOutput aria-hidden="true" />
            <span>{firstArtifact.title}</span>
          </Button>
        ) : null}

        {run.error?.code ? (
          <details className="conv-run-outcome__details">
            <summary>技术详情</summary>
            <code>{run.error.code}</code>
          </details>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

function outcomeTitle(
  outcome: "failed" | "partial" | "cancelled",
  artifactCount: number,
): string {
  const preserved = artifactCount > 0 ? "，已有结果仍可使用" : "";
  if (outcome === "failed") return `任务未完成${preserved}`;
  if (outcome === "partial") return `分析部分完成${preserved}`;
  return `任务已停止${preserved}`;
}
