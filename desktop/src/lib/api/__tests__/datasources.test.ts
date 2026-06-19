import { afterEach, describe, expect, it, vi } from "vitest";
import { datasourcesApi } from "../datasources";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("datasourcesApi", () => {
  it("posts LLM config when syncing schema AI metadata", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await datasourcesApi.syncSchema("ds-1", {
      api_key: "sk-test",
      api_base: "https://example.test/v1",
      model_name: "qwen-plus",
    });

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/datasources/ds-1/sync");
    expect(options?.method).toBe("POST");
    expect(JSON.parse(String(options?.body))).toEqual({
      api_key: "sk-test",
      api_base: "https://example.test/v1",
      model_name: "qwen-plus",
    });
  });
});
