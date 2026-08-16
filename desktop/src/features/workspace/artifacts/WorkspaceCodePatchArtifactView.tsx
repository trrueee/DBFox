import { FilePenLine, HardDrive, Hash, ShieldCheck } from "lucide-react";
import type { WorkspaceCodePatchArtifact } from "../../../types/agentArtifact";
import { Button } from "../../../components/ui";
import { useProjectState } from "../../projects/useProjectState";
import { useWorkspaceFileStore } from "../../../stores/workspaceFileStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { ArtifactCard } from "./ArtifactCard";
import "./WorkspaceCodePatchArtifactView.css";

function joinWorkspacePath(root: string, relativePath: string): string {
  const cleanRoot = root.replaceAll("\\", "/").split("/").filter(Boolean).join("/");
  const cleanRelative = relativePath.replaceAll("\\", "/").split("/").filter(Boolean).join("/");
  return `${cleanRoot}/${cleanRelative}`;
}

function shortHash(value: string): string {
  return value.length > 12 ? `${value.slice(0, 12)}…` : value;
}

export function WorkspaceCodePatchArtifactView({
  artifact,
}: {
  artifact: WorkspaceCodePatchArtifact;
}) {
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);
  const { activeProject } = useProjectState(activeProjectId);
  const workspaceRoot = activeProject?.workspace_root?.trim() || "";
  const canOpen = Boolean(workspaceRoot);

  return (
    <ArtifactCard
      className="workspace-code-patch-artifact"
      icon={<FilePenLine size={15} aria-hidden="true" />}
      title={artifact.title || artifact.relativePath}
      badge="Code Patch"
      tone="default"
      description={
        artifact.created
          ? "Workspace file was created atomically after CAS verification."
          : "Workspace file was atomically replaced after SHA-256 verification."
      }
      meta={
        <span className="workspace-code-patch-artifact__meta">
          <Hash size={12} aria-hidden="true" />
          <span title={artifact.newSha256}>{shortHash(artifact.newSha256)}</span>
          <HardDrive size={12} aria-hidden="true" />
          <span>{artifact.sizeBytes} B</span>
          <ShieldCheck size={12} aria-hidden="true" />
          <span>{artifact.created ? "created" : "replaced"}</span>
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
          <FilePenLine size={13} aria-hidden="true" />
          在项目文件视图打开
        </Button>
      }
    >
      <code className="workspace-code-patch-artifact__path">{artifact.relativePath}</code>
      {artifact.oldSha256 ? (
        <span className="workspace-code-patch-artifact__old">
          old {shortHash(artifact.oldSha256)}
        </span>
      ) : null}
    </ArtifactCard>
  );
}
