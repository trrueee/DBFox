import type { ConversationArtifact } from "../../../types/conversation";

export function isPrimaryConversationArtifact(artifact: ConversationArtifact): boolean {
  return artifact.visibility === "primary";
}

export function isDataFrameResultArtifact(artifact: ConversationArtifact): boolean {
  return artifact.type === "dbfox.data.result_view" || artifact.type === "dbfox.data.snapshot";
}

export function sortConversationArtifacts(
  artifacts: readonly ConversationArtifact[],
): ConversationArtifact[] {
  return [...artifacts].sort((left, right) => (
    left.version - right.version || left.id.localeCompare(right.id)
  ));
}
