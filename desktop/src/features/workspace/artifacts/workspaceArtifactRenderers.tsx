import { WorkspaceCodePatchArtifactView } from "./WorkspaceCodePatchArtifactView";
import { WorkspaceFileSnapshotArtifactView } from "./WorkspaceFileSnapshotArtifactView";
import type {
  ArtifactRendererContribution,
} from "./types";
import { asRecord, requiredString } from "./types";
import type {
  WorkspaceCodePatchArtifact,
  WorkspaceFileSnapshotArtifact,
} from "../../../types/agentArtifact";

function parseWorkspaceFileSnapshotPayload(
  value: unknown,
): WorkspaceFileSnapshotArtifact {
  const payload = asRecord(value);
  return {
    id: "",
    type: "dbfox.workspace.file_snapshot",
    schemaVersion: 1,
    title: "",
    relativePath: requiredString(payload.relativePath, "relativePath"),
    sizeBytes: typeof payload.sizeBytes === "number" ? payload.sizeBytes : 0,
    sha256: requiredString(payload.sha256, "sha256"),
    truncated: payload.truncated === true,
  };
}

function parseWorkspaceCodePatchPayload(
  value: unknown,
): WorkspaceCodePatchArtifact {
  const payload = asRecord(value);
  return {
    id: "",
    type: "dbfox.workspace.code_patch",
    schemaVersion: 1,
    title: "",
    relativePath: requiredString(payload.relativePath, "relativePath"),
    oldSha256: requiredString(payload.oldSha256, "oldSha256"),
    newSha256: requiredString(payload.newSha256, "newSha256"),
    sizeBytes: typeof payload.sizeBytes === "number" ? payload.sizeBytes : 0,
    created: payload.created === true,
  };
}

export const workspaceArtifactRenderers: ReadonlyArray<
  ArtifactRendererContribution<unknown>
> = [
  {
    type: "dbfox.workspace.file_snapshot",
    supportedSchemaVersions: [1],
    parsePayload: parseWorkspaceFileSnapshotPayload,
    render: (artifact) => {
      const model = {
        ...parseWorkspaceFileSnapshotPayload(artifact.payload),
        id: artifact.id,
        title: artifact.title,
      };
      return <WorkspaceFileSnapshotArtifactView artifact={model} />;
    },
  },
  {
    type: "dbfox.workspace.code_patch",
    supportedSchemaVersions: [1],
    parsePayload: parseWorkspaceCodePatchPayload,
    render: (artifact) => {
      const model = {
        ...parseWorkspaceCodePatchPayload(artifact.payload),
        id: artifact.id,
        title: artifact.title,
      };
      return <WorkspaceCodePatchArtifactView artifact={model} />;
    },
  },
];
