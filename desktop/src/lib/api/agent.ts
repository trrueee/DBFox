import {
  apiArtifactRepresentationReadApiV1ArtifactsArtifactIdRepresentationsRepresentationTypeReadPost,
  apiArtifactRepresentationsApiV1ArtifactsArtifactIdRepresentationsGet,
  apiArtifactRepresentationStreamApiV1ArtifactsArtifactIdRepresentationsRepresentationTypeStreamPost,
  apiLlmModelsApiV1AgentLlmModelsPost,
  apiLlmTestApiV1AgentLlmTestPost,
} from "./generated/sdk.gen";
import type {
  ArtifactRepresentationRequest,
  LlmModelsResponse,
  LlmTestResponse,
} from "./generated/types.gen";

function artifactFileName(disposition: string) {
  const fallback = /^attachment; filename="([A-Za-z0-9._-]+)"/i.exec(disposition)?.[1];
  const encoded = /;\s*filename\*=UTF-8''([^;\s]+)/i.exec(disposition)?.[1];
  if (!encoded) return fallback;
  try {
    return decodeURIComponent(encoded);
  } catch {
    return fallback;
  }
}

async function fetchArtifactFile(
  artifactId: string,
  representationType: string,
  value: ArtifactRepresentationRequest,
  signal?: AbortSignal,
  sessionId?: string,
  previewLimit?: number,
) {
  const { response } = await apiArtifactRepresentationStreamApiV1ArtifactsArtifactIdRepresentationsRepresentationTypeStreamPost({
    path: { artifact_id: artifactId, representation_type: representationType },
    body: value,
    query: sessionId ? { session_id: sessionId } : undefined,
    parseAs: "stream",
    signal,
    throwOnError: true,
  });
  const fileName = artifactFileName(response.headers.get("content-disposition") ?? "");
  if (previewLimit === undefined || !response.body) {
    return { blob: await response.blob(), fileName };
  }

  let received = 0;
  const bounded = response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      received += chunk.byteLength;
      if (received > previewLimit) throw new Error("文件超出预览大小，请下载查看。");
      controller.enqueue(chunk);
    },
  }));
  const contentType = response.headers.get("content-type");
  const headers = contentType ? { "content-type": contentType } : undefined;
  return { blob: await new Response(bounded, { headers }).blob(), fileName };
}

export const agentApi = {
  async listArtifactRepresentations(
    artifactId: string,
    signal?: AbortSignal,
    sessionId?: string,
  ) {
    const { data } = await apiArtifactRepresentationsApiV1ArtifactsArtifactIdRepresentationsGet({
      path: { artifact_id: artifactId },
      query: sessionId ? { session_id: sessionId } : undefined,
      signal,
      throwOnError: true,
    });
    return data;
  },

  async readArtifactRepresentation(
    artifactId: string,
    representationType: string,
    value: ArtifactRepresentationRequest,
    signal?: AbortSignal,
    sessionId?: string,
  ) {
    const { data } = await apiArtifactRepresentationReadApiV1ArtifactsArtifactIdRepresentationsRepresentationTypeReadPost({
      path: {
        artifact_id: artifactId,
        representation_type: representationType,
      },
      body: value,
      query: sessionId ? { session_id: sessionId } : undefined,
      signal,
      throwOnError: true,
    });
    return data;
  },

  async streamArtifactRepresentation(
    artifactId: string,
    representationType: string,
    value: ArtifactRepresentationRequest,
    signal?: AbortSignal,
    sessionId?: string,
  ): Promise<Blob> {
    const { blob } = await fetchArtifactFile(artifactId, representationType, value, signal, sessionId);
    return blob;
  },

  fetchArtifactFile,
};

export type { LlmTestResponse };

export async function testLlmConnection(
  llmCredentialId: string,
  apiBase: string,
  modelName?: string,
): Promise<LlmTestResponse> {
  const { data } = await apiLlmTestApiV1AgentLlmTestPost({
    body: {
      llm_credential_id: llmCredentialId,
      api_base: apiBase,
      model_name: modelName,
    },
    throwOnError: true,
  });
  return data;
}

export async function listLlmModels(
  llmCredentialId: string,
  apiBase: string,
): Promise<LlmModelsResponse> {
  const { data } = await apiLlmModelsApiV1AgentLlmModelsPost({
    body: {
      llm_credential_id: llmCredentialId,
      api_base: apiBase,
    },
    throwOnError: true,
  });
  return data;
}
