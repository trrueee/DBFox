import { afterEach, describe, expect, it, vi } from "vitest";
import { diagnosticsApi } from "../diagnostics";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("diagnosticsApi", () => {
  it("fetches diagnostic logs with a bounded line count", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          generated_at: "2026-06-20T00:00:00Z",
          policy: { redacted: true, max_lines_per_source: 25, omitted: [] },
          environment: { app: "DBFox" },
          sources: [],
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await diagnosticsApi.getLogs(25);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0][0])).toContain("/diagnostics/logs?max_lines=25");
    expect(result.policy.redacted).toBe(true);
  });
});
