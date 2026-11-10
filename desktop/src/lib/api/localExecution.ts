import {
  listExecutionJobsApiV1ConversationsConversationIdExecutionJobsGet,
  readExecutionJobApiV1ConversationsConversationIdExecutionJobsJobIdGet,
  stopExecutionJobApiV1ConversationsConversationIdExecutionJobsJobIdStopPost,
} from "./generated/sdk.gen";

export const localExecutionApi = {
  async list(conversationId: string, signal: AbortSignal) {
    const { data } = await listExecutionJobsApiV1ConversationsConversationIdExecutionJobsGet({
      path: { conversation_id: conversationId }, signal, throwOnError: true,
    });
    return data;
  },
  async read(conversationId: string, jobId: string, after: number, tail: boolean, signal: AbortSignal) {
    const { data } = await readExecutionJobApiV1ConversationsConversationIdExecutionJobsJobIdGet({
      path: { conversation_id: conversationId, job_id: jobId },
      query: { after, tail },
      signal, throwOnError: true,
    });
    return data;
  },
  async stop(conversationId: string, jobId: string) {
    await stopExecutionJobApiV1ConversationsConversationIdExecutionJobsJobIdStopPost({
      path: { conversation_id: conversationId, job_id: jobId }, throwOnError: true,
    });
  },
};
