export type {
  ArtifactEnvelope,
  ArtifactRepresentationAccess,
  ArtifactRepresentationDescriptor,
  ArtifactRepresentationRequest,
  ArtifactRepresentationResult,
  ArtifactViewContext,
  ArtifactViewContribution,
  ArtifactViewSurface,
} from "../../../../../sdk/frontend/index";

export function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Artifact payload must be an object");
  }
  return value as Record<string, unknown>;
}

export function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Artifact payload requires ${field}`);
  }
  return value;
}
