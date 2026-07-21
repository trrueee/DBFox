import type {
  ConversationActivity,
  ConversationArtifact,
  ConversationMessage,
  ConversationQuestion,
  ConversationRun,
} from "../../../types/conversation";

export type AssistantMessagePart =
  | { id: string; type: "activity"; activities: ConversationActivity[] }
  | { id: string; type: "error"; message: string }
  | { id: string; type: "cancelled" }
  | { id: string; type: "approval"; approval: NonNullable<ConversationRun["approval"]> }
  | { id: string; type: "question"; question: ConversationQuestion }
  | { id: string; type: "answer"; content: string; streaming: boolean }
  | { id: string; type: "artifacts"; artifacts: ConversationArtifact[] };

export function buildAssistantMessageParts({
  message,
  run,
  activities,
  artifacts,
  question,
  displayedAnswer,
}: {
  message: ConversationMessage;
  run?: ConversationRun;
  activities: ConversationActivity[];
  artifacts: ConversationArtifact[];
  question?: ConversationQuestion;
  displayedAnswer: string;
}): AssistantMessagePart[] {
  const parts: AssistantMessagePart[] = [];
  if (run && (activities.length > 0 || ["created", "queued", "running", "cancelling"].includes(run.status))) {
    parts.push({ id: `${run.id}:activity`, type: "activity", activities });
  }
  if (run?.status === "failed") {
    parts.push({
      id: `${run.id}:error`,
      type: "error",
      message: run.error_message || "本次分析未完成，请重试。",
    });
  }
  if (run?.status === "cancelled") {
    parts.push({ id: `${run.id}:cancelled`, type: "cancelled" });
  }
  if (run?.approval) {
    parts.push({ id: `${run.id}:approval:${run.approval.id}`, type: "approval", approval: run.approval });
  }
  if (question) {
    parts.push({ id: `${run?.id || message.id}:question:${question.id}`, type: "question", question });
  }
  if (displayedAnswer) {
    parts.push({
      id: `${message.id}:answer`,
      type: "answer",
      content: displayedAnswer,
      streaming: message.status === "streaming",
    });
  }
  if (artifacts.length > 0) {
    parts.push({ id: `${run?.id || message.id}:artifacts`, type: "artifacts", artifacts });
  }
  return parts;
}
