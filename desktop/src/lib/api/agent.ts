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

const requireBlob = (value: unknown): Blob => {
  if (!(value instanceof Blob)) {
    throw new TypeError("The export endpoint did not return a Blob.");
  }
  return value;
};

export const agentApi = {
  async listArtifactRepresentations(
    artifactId: string,
    signal?: AbortSignal,
  ) {
    const { data } = await apiArtifactRepresentationsApiV1ArtifactsArtifactIdRepresentationsGet({
      path: { artifact_id: artifactId },
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
  ) {
    const { data } = await apiArtifactRepresentationReadApiV1ArtifactsArtifactIdRepresentationsRepresentationTypeReadPost({
      path: {
        artifact_id: artifactId,
        representation_type: representationType,
      },
      body: value,
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
  ): Promise<Blob> {
    const { data } = await apiArtifactRepresentationStreamApiV1ArtifactsArtifactIdRepresentationsRepresentationTypeStreamPost({
      path: {
        artifact_id: artifactId,
        representation_type: representationType,
      },
      body: value,
      parseAs: "blob",
      signal,
      throwOnError: true,
    });
    return requireBlob(data);
  },

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
