import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { ProjectCreateForm } from "./ProjectCreateForm";
import "./ProjectCreateForm.css";

export function ProjectCreateDialog() {
  const projectCreateOpen = useWorkspaceStore((s) => s.projectCreateOpen);
  const setProjectCreateOpen = useWorkspaceStore((s) => s.setProjectCreateOpen);
  const closeProjectCreate = useWorkspaceStore((s) => s.closeProjectCreate);
  const setActiveProject = useWorkspaceStore((s) => s.setActiveProject);
  const showSmartQueryHome = useWorkspaceStore((s) => s.showSmartQueryHome);

  return (
    <Dialog open={projectCreateOpen} onOpenChange={setProjectCreateOpen}>
      <DialogContent className="project-create-dialog">
        <DialogHeader>
          <DialogTitle>打开文件夹</DialogTitle>
          <DialogDescription>
            在这个文件夹里开始对话，分析、创建、修改或研究任何事情。
          </DialogDescription>
        </DialogHeader>
        <ProjectCreateForm
          onCreated={(projectId) => {
            setActiveProject(projectId);
            closeProjectCreate();
            showSmartQueryHome();
          }}
          onCancel={closeProjectCreate}
        />
      </DialogContent>
    </Dialog>
  );
}
