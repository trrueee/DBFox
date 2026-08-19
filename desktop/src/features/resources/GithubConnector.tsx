import { useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  GitBranch,
  RefreshCw,
  Trash2,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui";
import type { ResourceConnectorContribution } from "./types";
import { useGithubStore } from "../github/githubStore";
import { useGithubDialogStore } from "./githubDialogStore";
import { githubApi } from "../../lib/api/github";
import type { GithubBindingResponse, GithubFileEntry } from "../../lib/api/generated/types.gen";

export const GITHUB_CONNECTOR_ID = "dbfox.github";

export function createGithubContribution(
  toast: (message: string) => void,
): ResourceConnectorContribution {
  return {
    id: GITHUB_CONNECTOR_ID,
    title: "GitHub",
    icon: <GitBranch size={13} aria-hidden="true" />,
    render: (context) => (
      <GithubConnectorContent projectId={context.projectId} toast={toast} />
    ),
    addLabel: "添加 GitHub 仓库",
    onAdd: (context) => useGithubDialogStore.getState().openAdd(context.projectId),
  };
}

function GithubConnectorContent({
  projectId,
  toast,
}: {
  projectId: string;
  toast: (message: string) => void;
}) {
  const bindings = useGithubStore((s) => s.bindingsByProject[projectId] ?? []);
  const activeBindingId = useGithubStore((s) => s.activeBindingIdByProject[projectId] ?? null);
  const loading = useGithubStore((s) => s.loadingByProject[projectId] ?? false);
  const loadBindings = useGithubStore((s) => s.loadBindings);
  const setActiveBindingId = useGithubStore((s) => s.setActiveBindingId);
  const refreshBinding = useGithubStore((s) => s.refreshBinding);
  const deleteBinding = useGithubStore((s) => s.deleteBinding);
  const openGithubFile = useGithubStore((s) => s.openGithubFile);

  const [refreshingId, setRefreshingId] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    void loadBindings(projectId);
  }, [projectId, loadBindings]);

  const activeBinding = bindings.find((b) => b.id === activeBindingId) ?? bindings[0] ?? null;

  const handleRefresh = async (e: React.MouseEvent, binding: GithubBindingResponse) => {
    e.stopPropagation();
    setRefreshingId(binding.id);
    try {
      await refreshBinding(projectId, binding.id);
      toast(`已更新 ${binding.owner}/${binding.repository} 最新提交`);
    } catch (err: unknown) {
      toast(`更新失败: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setRefreshingId(null);
    }
  };

  const handleDelete = async (e: React.MouseEvent, binding: GithubBindingResponse) => {
    e.stopPropagation();
    if (!window.confirm(`确定要移除仓库 ${binding.owner}/${binding.repository} 吗？`)) {
      return;
    }
    try {
      await deleteBinding(projectId, binding.id);
      toast(`已移除 ${binding.owner}/${binding.repository}`);
    } catch (err: unknown) {
      toast(`移除失败: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  if (loading && bindings.length === 0) {
    return <div className="ds-tree-status" role="status">正在加载 GitHub 仓库…</div>;
  }

  if (bindings.length === 0) {
    return (
      <div className="ds-tree-status">
        暂无关联的 GitHub 公开仓库，点击右上角 + 添加。
      </div>
    );
  }

  return (
    <div className="ds-entity-row__content ds-github-connector">
      {/* Repository selector / list */}
      <div className="ds-github-repo-list" role="list">
        {bindings.map((binding) => {
          const isActive = binding.id === activeBinding?.id;
          return (
            <div
              key={binding.id}
              className={`ds-github-repo-item ${isActive ? "is-active" : ""}`}
              onClick={() => setActiveBindingId(projectId, binding.id)}
            >
              <div className="ds-github-repo-item__header">
                <GitBranch size={13} className="ds-github-repo-icon" />
                <span className="ds-github-repo-name" title={`${binding.owner}/${binding.repository}`}>
                  {binding.owner}/{binding.repository}
                </span>
                <span className="ds-github-repo-badge" title={`分支: ${binding.ref_name}`}>
                  {binding.ref_name}
                </span>
                <div className="ds-github-repo-actions">
                  <button
                    type="button"
                    className="ds-tree-icon-btn"
                    title="拉取最新版本"
                    disabled={refreshingId === binding.id}
                    onClick={(e) => void handleRefresh(e, binding)}
                  >
                    <RefreshCw
                      size={12}
                      className={refreshingId === binding.id ? "animate-spin" : ""}
                    />
                  </button>
                  <button
                    type="button"
                    className="ds-tree-icon-btn ds-tree-icon-btn--danger"
                    title="移除仓库关联"
                    onClick={(e) => void handleDelete(e, binding)}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
              {isActive && binding.resolved_revision ? (
                <div className="ds-github-repo-revision">
                  rev: {binding.resolved_revision.slice(0, 7)}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* Active repository file explorer */}
      {activeBinding ? (
        <div className="ds-github-tree-section">
          <GithubRepoTree
            projectId={projectId}
            binding={activeBinding}
            onOpenFile={(path, name) => {
              openGithubFile({
                projectId,
                bindingId: activeBinding.id,
                owner: activeBinding.owner,
                repository: activeBinding.repository,
                revision: activeBinding.resolved_revision,
                filePath: path,
                fileName: name,
              });
            }}
          />
        </div>
      ) : null}
    </div>
  );
}

function GithubRepoTree({
  projectId,
  binding,
  onOpenFile,
}: {
  projectId: string;
  binding: GithubBindingResponse;
  onOpenFile: (path: string, name: string) => void;
}) {
  const [entries, setEntries] = useState<GithubFileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set([""]));
  const [subDirEntries, setSubDirEntries] = useState<Record<string, GithubFileEntry[]>>({});

  useEffect(() => {
    let cancelled = false;
    void githubApi
      .listFiles(projectId, binding.id, "")
      .then((res) => {
        if (!cancelled) {
          setEntries(res.entries);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, binding.id, binding.resolved_revision]);

  const toggleDir = useCallback(
    async (dirPath: string) => {
      setExpandedDirs((prev) => {
        const next = new Set(prev);
        if (next.has(dirPath)) {
          next.delete(dirPath);
        } else {
          next.add(dirPath);
        }
        return next;
      });

      if (!subDirEntries[dirPath]) {
        try {
          const res = await githubApi.listFiles(projectId, binding.id, dirPath);
          setSubDirEntries((prev) => ({ ...prev, [dirPath]: res.entries }));
        } catch {
          // ignore directory fetch error
        }
      }
    },
    [projectId, binding.id, subDirEntries],
  );

  if (loading) {
    return <div className="ds-tree-status" role="status">正在加载仓库文件列表…</div>;
  }

  if (error) {
    return <div className="ds-tree-status ds-tree-status--error" role="alert">{error}</div>;
  }

  if (entries.length === 0) {
    return <div className="ds-tree-status">仓库为空或无法获取文件列表。</div>;
  }

  return (
    <div className="ds-project-file-tree" role="tree" aria-label="GitHub 仓库文件">
      {entries.map((entry) => (
        <GithubTreeNode
          key={entry.path}
          entry={entry}
          depth={0}
          expandedDirs={expandedDirs}
          subDirEntries={subDirEntries}
          onToggleDir={toggleDir}
          onOpenFile={onOpenFile}
        />
      ))}
    </div>
  );
}

function GithubTreeNode({
  entry,
  depth,
  expandedDirs,
  subDirEntries,
  onToggleDir,
  onOpenFile,
}: {
  entry: GithubFileEntry;
  depth: number;
  expandedDirs: Set<string>;
  subDirEntries: Record<string, GithubFileEntry[]>;
  onToggleDir: (dirPath: string) => void;
  onOpenFile: (path: string, name: string) => void;
}) {
  const isDir = entry.type === "dir";
  const isExpanded = isDir && expandedDirs.has(entry.path);
  const children = subDirEntries[entry.path] ?? [];
  const fileName = entry.path.split("/").pop() || entry.path;

  return (
    <div>
      <button
        type="button"
        className={`hifi-tree-node ds-project-file-node ds-project-file-node--depth-${Math.min(depth, 10)}`}
        onClick={() => {
          if (isDir) {
            onToggleDir(entry.path);
          } else {
            onOpenFile(entry.path, fileName);
          }
        }}
      >
        {isDir ? (
          <span className="ds-project-file-node__expand">
            {isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          </span>
        ) : (
          <span className="ds-project-file-node__indent" />
        )}
        {isDir ? (
          <Folder size={12} className="ds-project-file-node__icon ds-project-file-node__icon--folder" />
        ) : (
          <FileText size={12} className="ds-project-file-node__icon ds-project-file-node__icon--file" />
        )}
        <span className="ds-project-file-node__name" title={entry.path}>
          {fileName}
        </span>
      </button>
      {isDir && isExpanded && (
        <div>
          {children.map((child) => (
            <GithubTreeNode
              key={child.path}
              entry={child}
              depth={depth + 1}
              expandedDirs={expandedDirs}
              subDirEntries={subDirEntries}
              onToggleDir={onToggleDir}
              onOpenFile={onOpenFile}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function AddGithubRepoDialog() {
  const { open, projectId, close } = useGithubDialogStore();
  const addBinding = useGithubStore((s) => s.addBinding);

  const [repoInput, setRepoInput] = useState("");
  const [refName, setRefName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanRepo = repoInput.trim();
    if (!cleanRepo) return;
    setSubmitting(true);
    setError(null);
    try {
      await addBinding(projectId, cleanRepo, refName.trim());
      setRepoInput("");
      setRefName("");
      close();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) close(); }}>
      <DialogContent className="ds-github-modal">
        <DialogHeader>
          <DialogTitle>添加 GitHub 公开仓库</DialogTitle>
          <DialogDescription>
            输入公开仓库所有者与仓库名（例如 astral-sh/uv）或完整 URL。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => void handleSubmit(e)}>
          <div className="ds-form-group">
            <label className="ds-form-label" htmlFor="github-repo-input">
              仓库标识 / URL
            </label>
            <input
              id="github-repo-input"
              type="text"
              className="ds-form-input"
              placeholder="owner/repo 或 https://github.com/owner/repo"
              value={repoInput}
              onChange={(e) => setRepoInput(e.target.value)}
              disabled={submitting}
              required
              autoFocus
            />
          </div>

          <div className="ds-form-group ds-form-group--spaced">
            <label className="ds-form-label" htmlFor="github-ref-input">
              分支 / 标签（留空自动使用默认分支）
            </label>
            <input
              id="github-ref-input"
              type="text"
              className="ds-form-input"
              placeholder="留空自动使用默认分支（如 main、master）"
              value={refName}
              onChange={(e) => setRefName(e.target.value)}
              disabled={submitting}
            />
          </div>

          {error ? (
            <div className="ds-form-error" role="alert">
              {error}
            </div>
          ) : null}

          <DialogFooter className="ds-modal-actions">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={close}
              disabled={submitting}
            >
              取消
            </button>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={submitting || !repoInput.trim()}
            >
              {submitting ? "正在解析并绑定…" : "确认添加"}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
