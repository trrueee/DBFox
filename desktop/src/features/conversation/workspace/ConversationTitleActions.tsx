import { useState } from "react";
import {
  PencilSimpleIcon,
} from "@/components/icons";
import { Alert, AlertDescription, Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Input, Label } from "../../../components/ui";
import { useConversationStore } from "../../../stores/conversationStore";
import { getUserErrorMessage } from "../../../lib/api/client";

export function ConversationTitleActions({ conversationId, title }: { conversationId: string; title: string }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(title);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const rename = useConversationStore(state => state.renameConversation);
  return <>
    <Button type="button" variant="ghost" size="icon-sm" className="titlebar-rename" aria-label="重命名对话" title="重命名对话"
      onClick={() => { setValue(title); setError(null); setOpen(true); }}><PencilSimpleIcon size={16} aria-hidden="true" /></Button>
    <Dialog open={open} onOpenChange={value => { if (!saving) setOpen(value); }}>
      <DialogContent>
        <form onSubmit={async event => {
          event.preventDefault();
          if (!value.trim() || saving) return;
          setSaving(true); setError(null);
          try { await rename(conversationId, value.trim()); setOpen(false); }
          catch (reason) { setError(reason); }
          finally { setSaving(false); }
        }}>
          <DialogHeader><DialogTitle>重命名对话</DialogTitle><DialogDescription>使用简短的名称，方便之后继续工作。</DialogDescription></DialogHeader>
          <div className="conversation-rename-field"><Label htmlFor="conversation-name">对话名称</Label>
            <Input id="conversation-name" value={value} onChange={event => setValue(event.target.value)} maxLength={80} disabled={saving} autoFocus />
          </div>
          {error ? <Alert variant="destructive"><AlertDescription>{getUserErrorMessage(error, "名称保存失败，请重试。")}</AlertDescription></Alert> : null}
          <DialogFooter><Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={saving}>取消</Button>
            <Button type="submit" disabled={!value.trim() || saving}>{saving ? "正在保存…" : "保存名称"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </>;
}
