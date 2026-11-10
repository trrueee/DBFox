import { queryOptions } from "@tanstack/react-query";
import {
  apiLocalModelStatusApiV1AgentLocalModelGet,
  apiLocalModelTestApiV1AgentLocalModelTestPost,
} from "./generated/sdk.gen";

export const localModelQuery = queryOptions({
  queryKey: ["local-model"],
  queryFn: async ({ signal }) => {
    const { data } = await apiLocalModelStatusApiV1AgentLocalModelGet({ signal, throwOnError: true });
    return data;
  },
  staleTime: 30_000,
});

export async function testLocalModel() {
  const { data } = await apiLocalModelTestApiV1AgentLocalModelTestPost({ throwOnError: true });
  return data;
}
