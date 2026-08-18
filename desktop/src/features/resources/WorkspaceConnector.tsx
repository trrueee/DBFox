import { useCallback, useEffect } from "react";
import { ChevronDown, ChevronRight, FileText, Folder } from "lucide-react";
import { useWorkspaceFileStore } from "../../stores/workspaceFileStore";
import type { ProjectFolderEntry, ProjectFolderListing } from "../../lib/projectFolder";
import { useProjectFolderTree } from "../projects/useProjectFolderTree";
import { useProjectState } from "../projects/useProjectState";
import type { ResourceConnectorContribution } from "./types";

export const WORKSPACE_CONNECTOR_ID = "dbfox.workspace";

export function createWorkspaceContribution(): ResourceConnectorContribution {
  return {
    id: WORKSPACE_CONNECTOR_ID,
    title: "文件",
    icon: <FileText size={13} aria-hidden="true" />,
    render: (context) => (
      <WorkspaceConnectorContent projectId={context.projectId} />
    ),
    // No addLabel/onAdd — no project update API exists yet
  };
}

function WorkspaceConnectorContent({ projectId }: { projectId: string }) {
  const openDockFile = useWorkspaceFileStore((s) => s.openFile);
  const { projects } = useProjectState(projectId);
  const activeProject = projects.find((project) => project.id === projectId) ?? null;
  const workspaceRoot = activeProject?.workspace_root?.trim() || "";

  const {
    listings: folderListings,
    loadingPaths: folderLoadingPaths,
    errors: folderErrors,
    expandedFolders,
    loadFolder,
    toggleFolder,
  } = useProjectFolderTree();

  useEffect(() => {
    if (!workspaceRoot) return;
    void loadFolder(workspaceRoot);
  }, [loadFolder, workspaceRoot]);

  const handleOpenFile = useCallback(
    (entry: ProjectFolderEntry) => {
      openDockFile(entry.path, entry.name, projectId);
    },
    [projectId, openDockFile],
  );

  if (!workspaceRoot) {
    return (
      <div className="ds-tree-status">该项目未关联本地文件夹，编辑项目以重新选择。</div>
    );
  }

  const listing = folderListings[workspaceRoot];
  const loading = folderLoadingPaths[workspaceRoot] && !listing;
  const folderError = folderErrors[workspaceRoot] && !listing;

  return (
    <div className="ds-entity-row__content ds-project-files">
      {loading ? (
        <div className="ds-tree-status" role="status">正在读取项目文件…</div>
      ) : folderError ? (
        <div className="ds-tree-status ds-tree-status--error" role="alert">{folderErrors[workspaceRoot]}</div>
      ) : listing?.entries.length === 0 ? (
        <div className="ds-tree-status">这个文件夹是空的。</div>
      ) : (
        <div className="ds-project-file-tree" role="tree" aria-label="项目文件">
          {listing?.entries.map((entry) => (
            <WorkspaceFileTreeNode
              key={entry.path}
              entry={entry}
              depth={0}
              listings={folderListings}
              loadingPaths={folderLoadingPaths}
              errors={folderErrors}
              expandedFolders={expandedFolders}
              onToggleFolder={toggleFolder}
              onOpenFile={handleOpenFile}
            />
          ))}
          {listing?.truncated ? (
            <div className="ds-tree-status ds-project-file-node__status">文件夹内容过多，只显示前 600 项。</div>
          ) : null}
        </div>
      )}
    </div>
  );
}

interface WorkspaceFileTreeNodeProps {
  entry: ProjectFolderEntry;
  depth: number;
  listings: Record<string, ProjectFolderListing | null>;
  loadingPaths: Record<string, boolean>;
  errors: Record<string, string>;
  expandedFolders: string[];
  onToggleFolder: (entry: ProjectFolderEntry) => void;
  onOpenFile: (entry: ProjectFolderEntry) => void;
}

function WorkspaceFileTreeNode({
  entry,
  depth,
  listings,
  loadingPaths,
  errors,
  expandedFolders,
  onToggleFolder,
  onOpenFile,
}: WorkspaceFileTreeNodeProps) {
  const depthClass = `ds-project-file-node--depth-${Math.min(depth, 10)}`;
  if (entry.isDir) {
    const expanded = expandedFolders.includes(entry.path);
    const listing = listings[entry.path];
    const loading = Boolean(loadingPaths[entry.path]);
    const error = errors[entry.path] ?? null;
    return (
      <div className="ds-project-file-node" role="treeitem" aria-expanded={expanded}>
        <button
          type="button"
          className={`ds-project-file-node__dir ${depthClass}`}
          onClick={() => onToggleFolder(entry)}
          title={entry.name}
        >
          {expanded ? (
            <ChevronDown size={12} className="ds-project-file-node__chevron" aria-hidden="true" />
          ) : (
            <ChevronRight size={12} className="ds-project-file-node__chevron" aria-hidden="true" />
          )}
          <Folder size={13} className="ds-project-file-node__icon" aria-hidden="true" />
          <span className="ds-project-file-node__name">{entry.name}</span>
        </button>
        {expanded ? (
          <div className="ds-project-file-node__children" role="group">
            {loading && !listing ? (
              <div className="ds-tree-status ds-project-file-node__status" role="status">正在读取…</div>
            ) : null}
            {error ? <div className="ds-tree-status ds-tree-status--error" role="alert">{error}</div> : null}
            {listing?.entries.length === 0 ? (
              <div className="ds-tree-status ds-project-file-node__status">空文件夹</div>
            ) : null}
            {listing?.entries.map((child) => (
              <WorkspaceFileTreeNode
                key={child.path}
                entry={child}
                depth={depth + 1}
                listings={listings}
                loadingPaths={loadingPaths}
                errors={errors}
                expandedFolders={expandedFolders}
                onToggleFolder={onToggleFolder}
                onOpenFile={onOpenFile}
              />
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={`ds-project-file-node ds-project-file-node--file ${depthClass}`}
      onClick={() => onOpenFile(entry)}
      title={entry.path}
    >
      <FileText size={13} className="ds-project-file-node__icon" aria-hidden="true" />
      <span className="ds-project-file-node__name">{entry.name}</span>
    </button>
  );
}
