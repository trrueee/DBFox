import type { ReactNode } from "react";

export interface ArtifactEnvelope<TPayload = Record<string, unknown>> {
  id: string;
  type: string;
  schema_version?: number;
  title: string;
  summary?: string | null;
  payload?: TPayload | null;
  payload_ref?: string | null;
  provenance?: Record<string, unknown>;
  relations?: Array<{ relation: string; artifact_id: string }>;
  status?: string;
  visibility?: string;
  version?: number;
}

export interface ArtifactRendererContext {
  onToast: (message: string) => void;
  compact?: boolean;
  mode?: "inline" | "workspace";
}

export interface ArtifactRendererContribution<TPayload> {
  type: string;
  supportedSchemaVersions: readonly number[];
  parsePayload(value: unknown): TPayload;
  render(
    artifact: ArtifactEnvelope<TPayload>,
    context: ArtifactRendererContext,
  ): ReactNode;
}

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
