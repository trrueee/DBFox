import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface PromptDialogProps {
  open: boolean;
  title: string;
  placeholder?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}

export function PromptDialog({ open, title, placeholder = "", confirmLabel = "确认", cancelLabel = "取消", onConfirm, onCancel }: PromptDialogProps) {
  const [value, setValue] = useState("");

  useEffect(() => { if (open) setValue(""); }, [open]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <DialogContent className="sm:max-w-[380px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <Input
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          onKeyDown={(e) => {
            if (e.key === "Enter" && value.trim()) { onConfirm(value.trim()); setValue(""); }
            if (e.key === "Escape") onCancel();
          }}
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => { onCancel(); setValue(""); }}>{cancelLabel}</Button>
          <Button onClick={() => { if (value.trim()) { onConfirm(value.trim()); setValue(""); } }} disabled={!value.trim()}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
