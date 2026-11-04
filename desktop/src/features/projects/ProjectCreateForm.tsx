import { useEffect, useRef, useState } from "react";
import { FolderOpen } from "lucide-react";
import { Alert, AlertDescription, AlertTitle, Button, ErrorDetails } from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";
import { pickDesktopProjectFolder } from "../../lib/desktopHost";
import { invokeBoundDlcOperation } from "../dlc/extensionHost";
import { useDlcStore } from "../dlc/extensionStore";
import { useProjectState } from "./useProjectState";
import "./ProjectCreateForm.css";

interface ProjectCreateFormProps { onCreated: (projectId: string) => void; onCancel: () => void }

// The native picker returns a realpath. Case folding is only valid for Windows paths.
function folderIdentity(path: string): string {
  const normalized = path.replaceAll(String.fromCharCode(92), "/").replace(/\/+$/, "");
  return /^(?:[a-z]:|\/\/)/i.test(normalized) ? normalized.toLowerCase() : normalized;
}

export function ProjectCreateForm({ onCreated, onCancel }: ProjectCreateFormProps) {
  const { projects, createProject, loadingProjects, projectError } = useProjectState("");
  const [path, setPath] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>();
  const mounted = useRef(true);
  const inFlight = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const openFolder = async () => {
    if (inFlight.current || loadingProjects) return;
    inFlight.current = true;
    setSubmitting(true); setError(undefined);
    try {
      if (projectError) throw projectError;
      const workspace = useDlcStore.getState().contributions.connectors.find(item => item.id === "dbfox.workspace");
      if (!workspace?.listResources) throw new Error("请先启用文件工作区扩展。");
      const selected = path || await pickDesktopProjectFolder();
      if (!selected || !mounted.current) return;
      setPath(selected);
      const identity = folderIdentity(selected);
      const inventories = await Promise.all(projects.map(async project => ({ project,
        resources: await workspace.listResources!({ projectId: project.id }),
      })));
      if (!mounted.current) return;
      const existing = inventories.find(item => item.resources.some(resource => folderIdentity(resource.name) === identity));
      if (existing) { onCreated(existing.project.id); return; }
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(identity));
      const key = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
      if (!mounted.current) return;
      const project = await createProject({ name: selected.split(/[\\/]/).filter(Boolean).at(-1) || "文件夹", description: null, idempotency_key: `folder:${key}` });
      if (!mounted.current) return;
      const result = await invokeBoundDlcOperation<{ binding: { root_path: string } | null }>("dbfox.workspace", "binding.get", {}, { projectId: project.id });
      if (!mounted.current) return;
      if (result.binding && folderIdentity(result.binding.root_path) !== identity) throw new Error("该工作区已关联其他文件夹。");
      if (!result.binding) await invokeBoundDlcOperation("dbfox.workspace", "binding.create", { root_path: selected }, { projectId: project.id });
      if (mounted.current) onCreated(project.id);
    } catch (reason) { if (mounted.current) setError(reason); }
    finally { inFlight.current = false; if (mounted.current) setSubmitting(false); }
  };

  return <div className="project-create__form">
    <div className="project-create__folder-summary"><FolderOpen size={20} aria-hidden="true" /><span>{path ? path.split(/[\\/]/).filter(Boolean).at(-1) : "选择你的工作文件夹"}</span>
      <p>{path || "对话、文件和成果围绕这个文件夹组织。"}</p></div>
    {error ? <Alert variant="destructive"><AlertTitle>打开文件夹失败</AlertTitle><AlertDescription><p>{getUserErrorMessage(error, "文件夹打开未完成，请重试。")}</p><ErrorDetails error={error} /></AlertDescription></Alert> : null}
    <div className="project-create__actions"><Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>取消</Button>
      <Button type="button" onClick={() => void openFolder()} disabled={submitting || loadingProjects}><FolderOpen size={16} aria-hidden="true" />{submitting ? "正在打开…" : path ? "重试打开" : "打开文件夹"}</Button></div>
  </div>;
}
