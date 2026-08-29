import type { ConversationArtifact } from "../../../types/conversation";

/**
 * "Primary" is the DLC-declared evidence semantic: the producing capability
 * marks an artifact primary at creation time, and the harness filters on
 * visibility alone — Core never enumerates capability-specific type names.
 */
export function isPrimaryConversationArtifact(artifact: ConversationArtifact): boolean {
  return artifact.visibility === "primary";
}

/** Shape check for data-result payloads (engine contract `dbfox.dataframe.v1`
 * carriers all project a `rowCount`). Type-agnostic by design. */
export function hasDataFramePayload(artifact: ConversationArtifact): boolean {
  const payload = artifact.payload as Record<string, unknown> | null | undefined;
  return typeof payload?.rowCount === "number" && Number.isFinite(payload.rowCount);
}

export function sortConversationArtifacts(
  artifacts: readonly ConversationArtifact[],
): ConversationArtifact[] {
  return [...artifacts].sort((left, right) => (
    left.version - right.version || left.id.localeCompare(right.id)
  ));
}
