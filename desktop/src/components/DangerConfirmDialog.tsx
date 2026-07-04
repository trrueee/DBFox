import { useState } from "react";
import { ShieldAlert, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import "./DangerConfirmDialog.css";

export interface ConfirmationDetails {
  confirm_token: string;
  impact_summary: string;
  expected_confirm_text: string;
  onConfirm: (confirmText: string) => Promise<void>;
  onCancel: () => void;
}

interface DangerConfirmDialogProps {
  details: ConfirmationDetails | null;
}

export const DangerConfirmDialog: React.FC<DangerConfirmDialogProps> = ({ details }) => {
  if (!details) return null;

  return (
    <Dialog open onOpenChange={(open) => { if (!open) details.onCancel(); }}>
      <DangerConfirmDialogContent key={details.confirm_token} details={details} />
    </Dialog>
  );
};

function DangerConfirmDialogContent({ details }: { details: ConfirmationDetails }) {
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleConfirm = async () => {
    if (inputText.trim() !== details.expected_confirm_text) {
      setError(`输入错误！请精确输入 '${details.expected_confirm_text}'`);
      return;
    }
    setLoading(true); setError("");
    try { await details.onConfirm(inputText); }
    catch (err: unknown) { setError(err instanceof Error ? err.message : "确认操作失败"); }
    finally { setLoading(false); }
  };

  return (
    <DialogContent className="danger-confirm-dialog-content">
      <DialogHeader>
        <div className="danger-confirm-dialog-title-row">
          <ShieldAlert size={20} className="danger-confirm-dialog-title-icon" />
          <DialogTitle>安全中心：高危操作二次确认</DialogTitle>
        </div>
      </DialogHeader>

      <div className="danger-confirm-dialog-body">
        <DialogDescription className="danger-confirm-dialog-summary">
          {details.impact_summary}
        </DialogDescription>

        <div className="danger-confirm-dialog-field">
          <Label className="danger-confirm-dialog-label">
            请输入 <code className="danger-confirm-dialog-code">{details.expected_confirm_text}</code> 以确认执行：
          </Label>
          <Input
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={details.expected_confirm_text}
            disabled={loading}
            className={inputText === details.expected_confirm_text
              ? "danger-confirm-dialog-input danger-confirm-dialog-input--valid"
              : "danger-confirm-dialog-input danger-confirm-dialog-input--invalid"}
          />
        </div>

        {error && (
          <div className="danger-confirm-dialog-warning">
            <ShieldAlert size={14} /> {error}
          </div>
        )}
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={details.onCancel} disabled={loading}>取消</Button>
        <Button variant="destructive" onClick={handleConfirm} disabled={loading || inputText.trim() !== details.expected_confirm_text}>
          {loading && <Loader2 size={14} className="danger-confirm-dialog-loading-icon" />}
          确认执行
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
