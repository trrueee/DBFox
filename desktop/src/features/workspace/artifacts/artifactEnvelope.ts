import type { ConversationArtifact } from "../../../types/conversation";
import type { ArtifactEnvelope } from "./types";

/**
 * Projects the canonical Conversation Artifact without interpreting its
 * capability-owned payload. This is the sole UI boundary between the durable
 * conversation projection and Artifact views.
 */
export function toArtifactEnvelope(artifact: ConversationArtifact): ArtifactEnvelope {
  return {
    id: artifact.id,
    type: artifact.type,
    schema_version: artifact.schema_version ?? 1,
    title: artifact.title,
    summary: artifact.summary,
    payload: artifact.payload as Record<string, unknown>,
    payload_ref: artifact.payload_ref,
    resource_refs: artifact.resource_refs,
    provenance: artifact.provenance,
    relations: artifact.relations,
    status: artifact.status,
    visibility: artifact.visibility,
    version: artifact.version,
  };
}
