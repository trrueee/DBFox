import { GitBranch, FileText, Hash, HardDrive, TriangleAlert } from "lucide-react";
import type { GithubFileSnapshotArtifact } from "../../../types/agentArtifact";
import { Button } from "../../../components/ui";
import { useGithubStore } from "../../github/githubStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { ArtifactCard } from "./ArtifactCard";
import "./WorkspaceFileSnapshotArtifactView.css";

export function GithubFileSnapshotArtifactView({
  artifact,
}: {
  artifact: GithubFileSnapshotArtifact;
}) {
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);
  const bindings = useGithubStore((s) => s.bindingsByProject[activeProjectId] ?? []);
  const binding = bindings.find((b) => b.id === artifact.repositoryBindingId);

  const owner = binding?.owner || "";
  const repository = binding?.repository || "";

  return (
    <ArtifactCard
      className="workspace-file-snapshot-artifact"
      icon={<GitBranch size={15} aria-hidden="true" />}
      title={artifact.title || artifact.relativePath}
      badge="GitHub Snapshot"
      tone="default"
      description="GitHub file snapshot metadata. Full content is fetched from the frozen commit revision, not persisted in the Artifact."
      meta={
        <span className="workspace-file-snapshot-artifact__meta">
          <GitBranch size={12} aria-hidden="true" />
          <span>{owner && repository ? `${owner}/${repository}@` : ""}{artifact.revision ? artifact.revision.slice(0, 7) : ""}</span>
          <Hash size={12} aria-hidden="true" />
          <span title={artifact.blobSha}>blob: {artifact.blobSha.slice(0, 7)}</span>
          <HardDrive size={12} aria-hidden="true" />
          <span>{artifact.sizeBytes} B</span>
          {artifact.truncated ? <TriangleAlert size={12} aria-hidden="true" /> : null}
        </span>
      }
      actions={
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            useGithubStore.getState().openGithubFile({
              projectId: activeProjectId,
              bindingId: artifact.repositoryBindingId,
              owner,
              repository,
              revision: artifact.revision,
              filePath: artifact.relativePath,
              fileName: artifact.title || artifact.relativePath,
            });
          }}
        >
          <FileText size={13} aria-hidden="true" />
          在 GitHub 文件视图打开
        </Button>
      }
    >
      <code className="workspace-file-snapshot-artifact__path">{artifact.relativePath}</code>
    </ArtifactCard>
  );
}
