import { fetchEnginePath } from "../../lib/api/client";
import { attachmentCapabilitiesApiV1AttachmentCapabilitiesGet } from "../../lib/api/generated/sdk.gen";
import { zAttachmentSummary } from "../../lib/api/generated/zod.gen";

export const ATTACHMENT_RESOURCE_KIND = "dbfox.core.attachment";

export async function attachmentCapabilities(signal?: AbortSignal) {
  const { data } = await attachmentCapabilitiesApiV1AttachmentCapabilitiesGet({ signal, throwOnError: true });
  return data;
}

async function requireOk(response: Response): Promise<void> {
  if (response.ok) return;
  const error: unknown = await response.json().catch(() => null);
  const detail = error && typeof error === "object" && "detail" in error ? error.detail : null;
  throw new Error(typeof detail === "string" ? detail : "附件操作未完成，请重试。");
}

export async function uploadAttachment(sessionId: string, name: string, bytes: Uint8Array, key: string, signal?: AbortSignal) {
  const response = await fetchEnginePath(`/conversations/${encodeURIComponent(sessionId)}/attachments`, {
    method: "POST", headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(name), "X-Upload-Key": key },
    body: new Uint8Array(bytes).buffer, signal,
  });
  await requireOk(response);
  return zAttachmentSummary.parse(await response.json());
}

export async function removeStagedAttachment(sessionId: string, attachmentId: string) {
  const response = await fetchEnginePath(`/conversations/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(attachmentId)}`, { method: "DELETE" });
  // Removing a reference to a sent file does not delete its historical source.
  if (response.status === 409 || response.status === 404) return;
  await requireOk(response);
}
