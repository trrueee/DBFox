import { AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

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
  const variantStyles = {
    danger: { iconBg: "bg-[hsl(var(--destructive)/0.1)]", iconColor: "text-[hsl(var(--destructive))]", btnVariant: "destructive" as const },
    warning: { iconBg: "bg-[hsl(var(--warning)/0.1)]", iconColor: "text-[hsl(var(--warning))]", btnVariant: "destructive" as const },
    info: { iconBg: "bg-[hsl(var(--primary)/0.1)]", iconColor: "text-[hsl(var(--primary))]", btnVariant: "default" as const },
  };
  const s = variantStyles[variant];

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <div className="flex items-start gap-3">
            <div className={`w-9 h-9 rounded flex items-center justify-center shrink-0 ${s.iconBg}`}>
              <AlertTriangle size={18} className={s.iconColor} />
            </div>
            <div>
              <DialogTitle>{title}</DialogTitle>
              <DialogDescription className="mt-1 whitespace-pre-wrap">{message}</DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>{cancelLabel}</Button>
          <Button variant={s.btnVariant} onClick={onConfirm}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
