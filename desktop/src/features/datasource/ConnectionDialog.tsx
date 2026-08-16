import { lazy, Suspense } from "react";
import { LoadingState } from "../../components/ui";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import "./ConnectionDialog.css";

const DataSourcesPage = lazy(() =>
  import("../../pages/DataSourcesPage").then((module) => ({ default: module.DataSourcesPage })),
);

interface ConnectionDialogProps {
  open: boolean;
  createMode: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ConnectionDialog({
  open,
  createMode,
  onOpenChange,
}: ConnectionDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="connection-dialog">
        <DialogHeader>
          <DialogTitle>
            {createMode ? "新建数据库连接" : "数据库连接管理"}
          </DialogTitle>
          <DialogDescription>
            连接只保存在本地；密码进入系统凭据库，不会写入项目状态。
          </DialogDescription>
        </DialogHeader>
        <Suspense fallback={<LoadingState label="正在载入连接管理" />}>
          <DataSourcesPage
            chrome="dialog"
            initialShowAddForm={createMode}
            onClose={() => onOpenChange(false)}
          />
        </Suspense>
      </DialogContent>
    </Dialog>
  );
}
