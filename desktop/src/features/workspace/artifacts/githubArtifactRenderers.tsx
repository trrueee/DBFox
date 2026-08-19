import { GithubFileSnapshotArtifactView } from "./GithubFileSnapshotArtifactView";
import type { ArtifactRendererContribution } from "./types";
import { asRecord, requiredString } from "./types";
import type { GithubFileSnapshotArtifact } from "../../../types/agentArtifact";

function parseGithubFileSnapshotPayload(
  value: unknown,
): GithubFileSnapshotArtifact {
  const payload = asRecord(value);
  return {
    id: "",
    type: "dbfox.github.file_snapshot",
    schemaVersion: 1,
    title: "",
    repositoryBindingId: requiredString(
      payload.repositoryBindingId,
      "repositoryBindingId",
    ),
    relativePath: requiredString(payload.relativePath, "relativePath"),
    revision: requiredString(payload.revision, "revision"),
    blobSha: requiredString(payload.blobSha, "blobSha"),
    sizeBytes: typeof payload.sizeBytes === "number" ? payload.sizeBytes : 0,
    truncated: payload.truncated === true,
  };
}

export const githubArtifactRenderers: ReadonlyArray<
  ArtifactRendererContribution<unknown>
> = [
  {
    type: "dbfox.github.file_snapshot",
    supportedSchemaVersions: [1],
    parsePayload: parseGithubFileSnapshotPayload,
    render: (artifact) => {
      const model = {
        ...parseGithubFileSnapshotPayload(artifact.payload),
        id: artifact.id,
        title: artifact.title,
      };
      return <GithubFileSnapshotArtifactView artifact={model} />;
    },
  },
];
