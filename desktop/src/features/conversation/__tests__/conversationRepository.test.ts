import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import {
  listConversations,
  saveConversation,
  deleteConversation,
  migrateLegacyConversations,
} from "../conversationRepository";
import type { Conversation } from "../../../types/conversation";
import { invoke } from "@tauri-apps/api/core";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

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

  it("migrateLegacyConversations does nothing if not in Tauri", async () => {
    vi.stubGlobal("window", {});
    await migrateLegacyConversations();
    expect(invoke).not.toHaveBeenCalled();
  });

  it("migrateLegacyConversations reads from Tauri and upserts to Engine if in Tauri", async () => {
    // Simulate Tauri environment
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });

    // Mock tauri list_conversations returning 1 conversation
    const mockRecord = {
      id: "legacy-1",
      title: "Legacy title",
      created_at: 1000,
      updated_at: 2000,
      context_tables_json: '["users"]',
      messages_json: "[]",
      artifacts_json: "[]",
    };
    vi.mocked(invoke).mockResolvedValueOnce([mockRecord]);

    // Mock successful put request
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));

    await migrateLegacyConversations();

    // Verify it invoked list_conversations Tauri command
    expect(invoke).toHaveBeenCalledWith("list_conversations");

    // Verify it sent PUT to engine
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/conversations/legacy-1");
    expect(options.method).toBe("PUT");

    // Verify migration marker is set
    expect(localStorage.getItem("dbfox_legacy_conversations_migrated")).toBe("true");

    // Running it again should not invoke Tauri command
    vi.mocked(invoke).mockClear();
    await migrateLegacyConversations();
    expect(invoke).not.toHaveBeenCalled();
  });
});
