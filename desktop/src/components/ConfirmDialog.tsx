import { AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import "./ConfirmDialog.css";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "warning" | "info";
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ open, title, message, confirmLabel = "确认", cancelLabel = "取消", variant = "info", onConfirm, onCancel }: ConfirmDialogProps) {
  const confirmVariant = variant === "info" ? "default" : "destructive";

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <DialogContent className="confirm-dialog-content">
        <DialogHeader>
          <div className="confirm-dialog-title-row">
            <div className={`confirm-dialog-icon confirm-dialog-icon--${variant}`}>
              <AlertTriangle size={18} className="confirm-dialog-icon-glyph" />
            </div>
            <div>
              <DialogTitle>{title}</DialogTitle>
              <DialogDescription className="confirm-dialog-message">{message}</DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>{cancelLabel}</Button>
          <Button variant={confirmVariant} onClick={onConfirm}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
