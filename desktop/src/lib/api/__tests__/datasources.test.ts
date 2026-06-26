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

  it("sends delete confirmation in the request body instead of the URL", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ success: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await datasourcesApi.deleteDatasource("ds-1", {
      token: "sensitive-token",
      text: "Production DB",
    });

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/datasources/ds-1");
    expect(String(url)).not.toContain("sensitive-token");
    expect(String(url)).not.toContain("Production%20DB");
    expect(options?.method).toBe("DELETE");
    expect(JSON.parse(String(options?.body))).toEqual({
      confirm_token: "sensitive-token",
      confirm_text: "Production DB",
    });
  });
});
