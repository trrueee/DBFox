import { afterEach, describe, expect, it, vi } from "vitest";
import { diagnosticsApi } from "../diagnostics";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("diagnosticsApi", () => {
  it("fetches diagnostic logs with a bounded line count", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json(
        {
          generated_at: "2026-06-20T00:00:00Z",
          policy: { redacted: true, max_lines_per_source: 25, omitted: [] },
          environment: { app: "DBFox" },
          sources: [],
          security_audit: { retention_days: 90, export_window_days: 7, max_records: 500, records: [] },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await diagnosticsApi.getLogs(25);

    expect(fetchMock).toHaveBeenCalledOnce();
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.url).toContain("/diagnostics/logs?max_lines=25");
    expect(result.policy.redacted).toBe(true);
  });

  it("sends the explicit confirmation text when clearing security audit", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ cleared: true, records_deleted: 3 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await diagnosticsApi.clearSecurityAudit("清空安全审计");

    expect(result.records_deleted).toBe(3);
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("POST");
    expect(await request.clone().json()).toEqual({ confirm_text: "清空安全审计" });
  });
});
