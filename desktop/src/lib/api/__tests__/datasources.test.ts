import { afterEach, describe, expect, it, vi } from "vitest";
import { datasourcesApi } from "../datasources";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("datasourcesApi", () => {
  it("syncs schema docs without AI metadata payload by default", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await datasourcesApi.syncSchema("ds-1");

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/datasources/ds-1/sync");
    expect(options?.method).toBe("POST");
    expect(options?.body).toBeUndefined();
  });
});
