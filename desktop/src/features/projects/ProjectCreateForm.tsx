import { useState, type FormEvent } from "react";
import { FolderOpen, FolderPlus } from "lucide-react";
import { Button, Input } from "../../components/ui";
import { useProjectState } from "./useProjectState";
import { pickProjectFolder } from "../../lib/projectFolder";
import { getUserErrorMessage } from "../../lib/api/client";
import "./ProjectCreateForm.css";

interface ProjectCreateFormProps {
  onCreated: (projectId: string) => void;
  onCancel: () => void;
}

export function ProjectCreateForm({ onCreated, onCancel }: ProjectCreateFormProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [folderPath, setFolderPath] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const { createProject } = useProjectState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("项目名称不能为空。");
      return;
    }
    if (!folderPath.trim()) {
      setError("请先选择项目文件夹。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const project = await createProject({
        name: trimmedName,
        description: description.trim() || null,
        workspace_root: folderPath.trim(),
      });
      onCreated(project.id);
    } catch (submitError) {
      setError(getUserErrorMessage(submitError, "创建项目失败，请重试。"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="project-create__form" onSubmit={(event) => void handleSubmit(event)}>
      <div className="project-create__field">
        <span className="project-create__label">项目文件夹</span>
        <button
          type="button"
          className="project-create__folder-picker"
          onClick={() => {
            setError("");
            void pickProjectFolder().then((path) => {
              if (!path) return;
              setFolderPath(path);
              if (!name.trim()) {
                const segments = path
                  .split("\\")
                  .flatMap((part) => part.split("/"))
                  .filter(Boolean);
                const candidate = segments[segments.length - 1] || path;
                setName(candidate);
              }
            }).catch(() => setError("仅在桌面应用中支持选择本地文件夹。"));
          }}
        >
          <FolderOpen size={14} aria-hidden="true" />
          {folderPath ? "重新选择文件夹" : "选择文件夹"}
        </button>
        {folderPath ? <span className="project-create__folder-path">{folderPath}</span> : null}
      </div>
      <label className="project-create__field">
        <span className="project-create__label">项目名称</span>
        <Input
          autoFocus
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="例如：电商经营分析"
          maxLength={128}
          disabled={submitting}
        />
      </label>
      <label className="project-create__field">
        <span className="project-create__label">项目描述（可选）</span>
        <Input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="这个项目主要分析什么？"
          maxLength={2_000}
          disabled={submitting}
        />
      </label>
      {error ? <div className="project-create__error" role="alert">{error}</div> : null}
      <div className="project-create__actions">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
          取消
        </Button>
        <Button type="submit" disabled={submitting}>
          <FolderPlus size={14} aria-hidden="true" />
          {submitting ? "正在创建…" : "创建项目"}
        </Button>
      </div>
    </form>
  );
}
