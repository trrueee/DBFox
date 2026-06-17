import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import {
  listConversations,
  saveConversation,
  deleteConversation,
  migrateLegacyConversations,
} from "../conversationRepository";
import type { Conversation } from "../../../types/conversation";
describe("conversationRepository", () => {
  let fetchMock: Mock;

  beforeEach(() => {
    fetchMock = vi.fn(async () => new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("listConversations requests GET /conversations", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }));
    const result = await listConversations();
    expect(result).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/conversations");
    expect(options.method).toBeUndefined(); // defaults to GET
  });

  it("saveConversation requests PUT /conversations/:id", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    const conv: Conversation = {
      id: "conv-1",
      title: "Title",
      createdAt: 1000,
      updatedAt: 2000,
      contextTables: ["users"],
      messages: [],
      artifacts: [],
    };
    await saveConversation(conv);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/conversations/conv-1");
    expect(options.method).toBe("PUT");
    const body = JSON.parse(options.body);
    expect(body.id).toBe("conv-1");
    expect(body.title).toBe("Title");
  });

  it("deleteConversation requests DELETE /conversations/:id", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    await deleteConversation("conv-1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/conversations/conv-1");
    expect(options.method).toBe("DELETE");
  });

  it("migrateLegacyConversations sets migrated flag and is idempotent", async () => {
    vi.stubGlobal("window", {});
    localStorage.removeItem("dbfox_legacy_conversations_migrated");

    await migrateLegacyConversations();
    expect(localStorage.getItem("dbfox_legacy_conversations_migrated")).toBe("true");

    // Second call is a no-op — flag already set
    await migrateLegacyConversations();
    expect(localStorage.getItem("dbfox_legacy_conversations_migrated")).toBe("true");
  });
});
