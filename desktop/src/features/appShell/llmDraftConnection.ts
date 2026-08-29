import { listLlmModels, testLlmConnection } from "../../lib/api/agent";
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

export interface DraftLlmModelList {
  ok: boolean;
  models: string[];
  message?: string;
}

/**
 * Fetches the model list an unsaved draft's endpoint exposes, using the same
 * short-lived credential lease as the connection test. The raw key never
 * leaves the engine.
 */
export async function listDraftLlmModels(draft: LlmConfigDraft): Promise<DraftLlmModelList> {
  const llm = buildLlmTestValues(draft);
  const apiKey = draft.apiKey.trim();
  if (!apiKey && !llm.llmCredentialId) {
    return { ok: false, models: [], message: "填写 API Key 后即可获取该服务的模型列表。" };
  }

  let credentialId = llm.llmCredentialId;
  let leaseId: string | null = null;
  if (apiKey) {
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
    credentialId = credential.id;
    leaseId = enrollment.lease_id;
  }

  try {
    const result = await listLlmModels(credentialId, llm.apiBase);
    if (!result.ok) {
      return { ok: false, models: [], message: result.error_message ?? "无法获取模型列表。" };
    }
    return { ok: true, models: (result.models ?? []).map((model) => model.id) };
  } finally {
    if (leaseId) {
      await releaseCredentialLease(leaseId).catch(() => undefined);
    }
  }
}
