import { beforeEach, describe, expect, it, vi } from "vitest";
import { createConversation, listConversations } from "../conversationRepository";

vi.mock("../../../lib/api/client", () => ({
  request: vi.fn(),
  BASE_URL: "http://127.0.0.1:8000/api/v1",
  ENGINE_TOKEN: "test-token",
}));

const { request } = await import("../../../lib/api/client");

describe("conversationRepository", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("lists structured conversation summaries", async () => {
    vi.mocked(request).mockResolvedValueOnce([
      {
        id: "conv-1",
        title: "Orders",
        datasource_id: "ds-1",
        updated_at: "2026-06-21T00:00:00+00:00",
        last_message: "Done",
        message_count: 2,
        run_status: "completed",
        artifact_count: 3,
      },
    ]);

    const result = await listConversations();

    expect(result[0].id).toBe("conv-1");
    expect(result[0].message_count).toBe(2);
    expect(request).toHaveBeenCalledWith("/conversations");
  });

  it("creates a conversation through the structured endpoint", async () => {
    vi.mocked(request).mockResolvedValueOnce({
      id: "conv-2",
      title: "New",
      datasource_id: "ds-1",
      context_tables: ["orders"],
      created_at: null,
      updated_at: null,
      messages: [],
      runs: [],
      artifacts: [],
      approvals: [],
    });

    const result = await createConversation({
      datasource_id: "ds-1",
      title: "New",
      context_tables: ["orders"],
    });

    expect(result.id).toBe("conv-2");
    expect(request).toHaveBeenCalledWith("/conversations", {
      method: "POST",
      body: JSON.stringify({ datasource_id: "ds-1", title: "New", context_tables: ["orders"] }),
    });
  });
});
