import { FileText, Hash, HardDrive, TriangleAlert } from "lucide-react";
import type { WorkspaceFileSnapshotArtifact } from "../../../types/agentArtifact";
import { Button } from "../../../components/ui";
import { useProjectState } from "../../projects/useProjectState";
import { useWorkspaceFileStore } from "../../../stores/workspaceFileStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { ArtifactCard } from "./ArtifactCard";
import "./WorkspaceFileSnapshotArtifactView.css";

function joinWorkspacePath(root: string, relativePath: string): string {
  const cleanRoot = root.replaceAll("\\", "/").split("/").filter(Boolean).join("/");
  const cleanRelative = relativePath.replaceAll("\\", "/").split("/").filter(Boolean).join("/");
  return `${cleanRoot}/${cleanRelative}`;
}

export function WorkspaceFileSnapshotArtifactView({
  artifact,
}: {
  artifact: WorkspaceFileSnapshotArtifact;
}) {
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);
  const { activeProject } = useProjectState(activeProjectId);
  const workspaceRoot = activeProject?.workspace_root?.trim() || "";
  const canOpen = Boolean(workspaceRoot);

  return (
    <ArtifactCard
      className="workspace-file-snapshot-artifact"
      icon={<FileText size={15} aria-hidden="true" />}
      title={artifact.title || artifact.relativePath}
      badge="File Snapshot"
      tone="default"
      description="Workspace file snapshot metadata. Full content is opened from the approved project folder, not persisted in the Artifact."
      meta={
        <span className="workspace-file-snapshot-artifact__meta">
          <Hash size={12} aria-hidden="true" />
          <span title={artifact.sha256}>{artifact.sha256.slice(0, 12)}…</span>
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
          disabled={!canOpen}
          onClick={() => {
            if (!workspaceRoot) return;
            useWorkspaceFileStore
              .getState()
              .openFile(joinWorkspacePath(workspaceRoot, artifact.relativePath), artifact.title, activeProjectId);
          }}
        >
          <FileText size={13} aria-hidden="true" />
          在项目文件视图打开
        </Button>
      }
    >
      <code className="workspace-file-snapshot-artifact__path">{artifact.relativePath}</code>
    </ArtifactCard>
  );
}
