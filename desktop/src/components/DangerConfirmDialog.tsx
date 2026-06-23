import { useState, useEffect } from "react";
import { ShieldAlert, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { if (details) { setInputText(""); setError(""); } }, [details]);

  if (!details) return null;

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
    <Dialog open onOpenChange={() => details.onCancel()}>
      <DialogContent className="sm:max-w-[500px] border-[hsl(var(--destructive))]">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <ShieldAlert size={20} className="text-[hsl(var(--destructive))]" />
            <DialogTitle>安全中心：高危操作二次确认</DialogTitle>
          </div>
        </DialogHeader>

        <div className="space-y-4">
          <div className="whitespace-pre-wrap text-[var(--ui-font-body)] leading-relaxed p-3.5 rounded border bg-[hsl(var(--muted))] max-h-[250px] overflow-auto">
            {details.impact_summary}
          </div>

          <div className="space-y-1.5">
            <Label className="text-[hsl(var(--destructive))] font-semibold">
              请输入 <code className="bg-[hsl(var(--destructive)/0.15)] px-1.5 py-0.5 rounded font-mono">{details.expected_confirm_text}</code> 以确认执行：
            </Label>
            <Input
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={details.expected_confirm_text}
              disabled={loading}
              className={inputText === details.expected_confirm_text ? "border-[hsl(var(--success))]" : "border-[hsl(var(--destructive))]"}
            />
          </div>

          {error && (
            <div className="flex items-center gap-1.5 text-[var(--ui-font-body)] text-[hsl(var(--destructive))]">
              <ShieldAlert size={14} /> {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={details.onCancel} disabled={loading}>取消</Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={loading || inputText.trim() !== details.expected_confirm_text}>
            {loading && <Loader2 size={14} className="animate-spin" />}
            确认执行
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
