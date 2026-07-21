import { testLlmConnection } from "../../lib/api/agent";
import { enrollCredentials, releaseCredentialLease } from "../../lib/api/credentials";
import type { LlmConfigDraft } from "../../lib/api/types/config";
import { buildLlmTestValues } from "../../lib/llmConfig";

/**
 * Tests an unsaved draft without persisting its raw API key. A draft key is
 * enrolled as a server-owned lease and released after either outcome.
 */
export async function testDraftLlmConnection(draft: LlmConfigDraft) {
  const llm = buildLlmTestValues(draft);
  const apiKey = draft.apiKey.trim();
  if (!apiKey) {
    return testLlmConnection(llm.llmCredentialId, llm.apiBase, llm.modelName);
  }

  const enrollment = await enrollCredentials([
    { kind: "llm_api_key", secret: apiKey },
  ]);
  if (!enrollment) {
    throw new Error("无法创建临时 LLM 凭据。");
  }
  const credential = enrollment.credentials.find((reference) => reference.kind === "llm_api_key");
  if (!credential) {
    await releaseCredentialLease(enrollment.lease_id).catch(() => undefined);
    throw new Error("临时 LLM 凭据无效。");
  }

  try {
    return await testLlmConnection(credential.id, llm.apiBase, llm.modelName);
  } finally {
    await releaseCredentialLease(enrollment.lease_id).catch(() => undefined);
  }
}
