import { afterEach, describe, expect, it, vi } from "vitest";
import { datasourcesApi } from "../datasources";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("datasourcesApi", () => {
  it("syncs schema docs without AI metadata payload by default", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await datasourcesApi.syncSchema("ds-1");

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.url).toContain("/datasources/ds-1/sync");
    expect(request.method).toBe("POST");
    expect(await request.clone().text()).toBe("");
  });

  it("sends delete confirmation in the request body instead of the URL", async () => {
    const fetchMock = vi.fn(async () => Response.json({ success: true, message: "deleted" }));
    vi.stubGlobal("fetch", fetchMock);

    await datasourcesApi.deleteDatasource("ds-1", {
      confirm_token: "sensitive-token",
      confirm_text: "Production DB",
    });

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.url).toContain("/datasources/ds-1");
    expect(request.url).not.toContain("sensitive-token");
    expect(request.url).not.toContain("Production%20DB");
    expect(request.method).toBe("DELETE");
    expect(await request.clone().json()).toEqual({
      confirm_token: "sensitive-token",
      confirm_text: "Production DB",
    });
  });
});
