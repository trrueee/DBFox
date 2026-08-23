import {
  apiAgentChartDataApiV1ArtifactsArtifactIdChartDataPost,
  apiLlmTestApiV1AgentLlmTestPost,
  apiAgentResultExportApiV1ArtifactsArtifactIdExportPost,
  apiAgentResultPageApiV1ArtifactsArtifactIdPagePost,
} from "./generated/sdk.gen";
import type {
  LlmTestResponse,
  ResultExportRequest,
  ResultPageRequest,
} from "./generated/types.gen";

const requireBlob = (value: unknown): Blob => {
  if (!(value instanceof Blob)) {
    throw new TypeError("The export endpoint did not return a Blob.");
  }
  return value;
};

export const agentApi = {
  async fetchArtifactPage(
    artifactId: string,
    value: ResultPageRequest,
    signal?: AbortSignal,
  ) {
    const { data } = await apiAgentResultPageApiV1ArtifactsArtifactIdPagePost({
      path: { artifact_id: artifactId },
      body: value,
      signal,
      throwOnError: true,
    });
    return data;
  },

  async fetchArtifactChartData(artifactId: string) {
    const { data } = await apiAgentChartDataApiV1ArtifactsArtifactIdChartDataPost({
      path: { artifact_id: artifactId },
      throwOnError: true,
    });
    return data;
  },

  async exportArtifactCsv(
    artifactId: string,
    value: ResultExportRequest,
  ): Promise<Blob> {
    const { data } = await apiAgentResultExportApiV1ArtifactsArtifactIdExportPost({
      path: { artifact_id: artifactId },
      body: value,
      parseAs: "blob",
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
