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
          <DialogTitle>新建项目</DialogTitle>
          <DialogDescription>
            项目用于组织长期上下文与 Agent 工作。创建后可继续添加文件、数据和外部服务。
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
