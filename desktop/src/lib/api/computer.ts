import { queryOptions } from "@tanstack/react-query";
import {
  listComputerSharesApiV1ConversationsConversationIdComputerGet,
  listComputerTargetsApiV1ComputerTargetsGet,
  previewComputerTargetApiV1ConversationsConversationIdComputerTargetIdPreviewGet,
  revokeComputerTargetApiV1ConversationsConversationIdComputerTargetIdDelete,
  shareComputerTargetApiV1ConversationsConversationIdComputerPost,
  stopComputerTargetApiV1ConversationsConversationIdComputerTargetIdStopPost,
  stopAllComputerTargetsApiV1ComputerStopPost,
  readComputerBrowserApiV1ConversationsConversationIdComputerTargetIdBrowserGet,
} from "./generated/sdk.gen";
import type { ShareInput } from "./generated/types.gen";

export const COMPUTER_RESOURCE_KIND = "dbfox.computer.target";
export const COMPUTER_REPRESENTATION = "dbfox.computer.capture.v1";

export const computerSharesQuery = (conversationId: string) => queryOptions({
  queryKey: ["computer-shares", conversationId],
  queryFn: async ({ signal }) => (await listComputerSharesApiV1ConversationsConversationIdComputerGet({
    path: { conversation_id: conversationId }, signal, throwOnError: true,
  })).data,
  enabled: Boolean(conversationId), retry: false, refetchInterval: 2000,
});

export const computerTargetsQuery = queryOptions({
  queryKey: ["computer-targets"], retry: false, staleTime: 0, gcTime: 0,
  queryFn: async ({ signal }) => (await listComputerTargetsApiV1ComputerTargetsGet({ signal, throwOnError: true })).data,
});

export async function shareComputer(conversationId: string, input: ShareInput) {
  return (await shareComputerTargetApiV1ConversationsConversationIdComputerPost({
    path: { conversation_id: conversationId }, body: input, throwOnError: true,
  })).data;
}

export async function stopComputer(conversationId: string, targetId: string, revoke = false) {
  const options = { path: { conversation_id: conversationId, target_id: targetId }, throwOnError: true as const };
  if (revoke) await revokeComputerTargetApiV1ConversationsConversationIdComputerTargetIdDelete(options);
  else await stopComputerTargetApiV1ConversationsConversationIdComputerTargetIdStopPost(options);
}

export async function previewComputer(conversationId: string, targetId: string, signal?: AbortSignal) {
  const { data } = await previewComputerTargetApiV1ConversationsConversationIdComputerTargetIdPreviewGet({
    path: { conversation_id: conversationId, target_id: targetId }, signal, parseAs: "blob", throwOnError: true,
  });
  if (!(data instanceof Blob) || data.type !== "image/png") throw new Error("画面没有返回可用的图片。");
  return data;
}

export async function stopAllComputer() {
  await stopAllComputerTargetsApiV1ComputerStopPost({ throwOnError: true });
}

export async function readBrowserState(conversationId: string, targetId: string, signal?: AbortSignal) {
  return (await readComputerBrowserApiV1ConversationsConversationIdComputerTargetIdBrowserGet({
    path: { conversation_id: conversationId, target_id: targetId }, signal, throwOnError: true,
  })).data;
}
