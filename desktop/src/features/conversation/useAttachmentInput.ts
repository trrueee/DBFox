import { useEffect, useRef, useState } from "react";
import type { WorkbenchReference } from "../../types/workspace";
import { selectActiveWorkbenchScopeId, useWorkspaceStore } from "../../stores/workspaceStore";
import { pickDesktopFile, readDesktopPickedFile } from "../../lib/desktopHost";
import { getUserErrorMessage } from "../../lib/api/client";
import { attachmentCapabilities, ATTACHMENT_RESOURCE_KIND, removeStagedAttachment, uploadAttachment } from "./attachmentRepository";
import { attachmentExtensions } from "./attachmentDock";

type PendingUpload = { scope: string; sessionId: string; name: string; bytes: Uint8Array; key: string };

/** UI request lifecycle only. Server ownership and admission remain authoritative. */
export function useAttachmentInput(ensureConversation: () => Promise<string>, references: readonly WorkbenchReference[]) {
  const scope = useWorkspaceStore(selectActiveWorkbenchScopeId);
  const active = useRef<{ scope: string; controller: AbortController } | null>(null);
  const retry = useRef<PendingUpload | null>(null);
  const [state, setState] = useState<{ scope: string; busy: boolean; error?: string; retryable?: boolean }>({ scope: "", busy: false });
  useEffect(() => () => { active.current?.controller.abort(); retry.current = null; }, []);
  useEffect(() => {
    if (active.current && active.current.scope !== scope) active.current.controller.abort();
    if (retry.current && retry.current.scope !== scope) retry.current = null;
  }, [scope]);

  const perform = async (again = false) => {
    if (active.current) return;
    const workspace = useWorkspaceStore.getState();
    const capturedScope = workspace.ensureActiveWorkbenchScope();
    const controller = new AbortController();
    active.current = { scope: capturedScope, controller };
    const current = () => !controller.signal.aborted && selectActiveWorkbenchScopeId(useWorkspaceStore.getState()) === capturedScope;
    setState({ scope: capturedScope, busy: true });
    try {
      if (references.some(ref => ref.object?.kind === ATTACHMENT_RESOURCE_KIND)) throw new Error("每条消息可添加一份文件，请先移除当前文件。");
      let pending = again ? retry.current : null;
      if (!pending) {
        retry.current = null;
        const accept = attachmentExtensions();
        if (!accept.length) throw new Error("没有可用的文件处理扩展，请先启用对应扩展。");
        const limits = await attachmentCapabilities(controller.signal);
        if (!current()) return;
        const selected = await pickDesktopFile({ title: "添加对话文件", filters: [{ name: "支持的文件", extensions: accept }], maxBytes: limits.max_file_bytes });
        if (!selected || !current()) return;
        if (selected.sizeBytes > limits.max_file_bytes) throw new Error("文件超过当前附件大小限制。");
        if (!accept.includes(selected.name.split(".").at(-1)?.toLowerCase() ?? "")) throw new Error("此文件格式暂不支持。");
        const bytes = await readDesktopPickedFile(selected.path);
        if (!current()) return;
        const sessionId = await ensureConversation();
        if (!current()) return;
        pending = { scope: capturedScope, sessionId, name: selected.name, bytes, key: crypto.randomUUID() };
        retry.current = pending;
      }
      if (!current() || pending.scope !== capturedScope) return;
      const uploaded = await uploadAttachment(pending.sessionId, pending.name, pending.bytes, pending.key, controller.signal);
      if (!current()) return;
      workspace.addWorkbenchReference({ label: uploaded.display_name,
        object: { kind: ATTACHMENT_RESOURCE_KIND, id: uploaded.id, version: uploaded.content_sha256 } });
      retry.current = null;
    } catch (reason) {
      if (current()) setState({ scope: capturedScope, busy: false, error: getUserErrorMessage(reason, "添加文件失败，请重试。"), retryable: Boolean(retry.current) });
      return;
    } finally {
      active.current = null;
      if (current()) setState(previous => previous.scope === capturedScope ? { ...previous, busy: false } : previous);
    }
  };

  const remove = (reference: WorkbenchReference, sessionId?: string) => {
    const capturedScope = selectActiveWorkbenchScopeId(useWorkspaceStore.getState());
    if (sessionId && reference.object?.kind === ATTACHMENT_RESOURCE_KIND) {
      void removeStagedAttachment(sessionId, reference.object.id).catch(() => {
        if (selectActiveWorkbenchScopeId(useWorkspaceStore.getState()) === capturedScope)
          setState({ scope: capturedScope, busy: false, error: "附件已从草稿移除，临时文件将稍后清理。" });
      });
    }
  };
  return { busy: state.scope === scope && state.busy, error: state.scope === scope ? state.error : undefined,
    retryable: state.scope === scope && state.retryable, add: () => perform(), retry: () => perform(true), remove };
}
