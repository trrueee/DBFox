import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api/client";
import { DiagnosticsPage } from "../DiagnosticsPage";

const { clearLogsMock, getLogsMock } = vi.hoisted(() => ({
  clearLogsMock: vi.fn(),
  getLogsMock: vi.fn(),
}));

vi.mock("../../lib/api/diagnostics", () => ({
  diagnosticsApi: {
    getLogs: getLogsMock,
    clearLogs: clearLogsMock,
    clearSecurityAudit: vi.fn(),
  },
}));

vi.mock("../../lib/diagnostics/clientLog", () => ({
  getClientLogSource: () => ({
    name: "frontend-client",
    path: "localStorage:dbfox-client-log",
    exists: false,
    size_bytes: 0,
    modified_at: null,
    content: "",
  }),
}));

vi.mock("../../lib/desktopHost", () => ({
  isEngineDesktopHost: () => false,
  exportDesktopDiagnosticBundle: vi.fn(),
}));

describe("DiagnosticsPage log viewer", () => {
  const onToast = vi.fn();
  const writeText = vi.fn();

  beforeEach(() => {
    onToast.mockReset();
    writeText.mockReset().mockResolvedValue(undefined);
    clearLogsMock.mockReset().mockResolvedValue({ cleared: false, sources_cleared: [] });
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    getLogsMock.mockReset().mockResolvedValue({
      generated_at: "2026-08-27T10:00:00Z",
      policy: { redacted: true, max_lines_per_source: 300, omitted: [] },
      environment: { app: "DBFox", pid: 42, python: "3.13", frozen: false },
      sources: [{
        name: "engine",
        path: "runtime/engine.log",
        exists: true,
        size_bytes: 320,
        modified_at: "2026-08-27T10:00:00Z",
        content: [
          JSON.stringify({ timestamp: "2026-08-27T09:59:58Z", level: "INFO", logger: "engine", message: "engine ready" }),
          JSON.stringify({ timestamp: "2026-08-27T09:59:59Z", level: "WARNING", logger: "database", message: "connection timeout" }),
          JSON.stringify({ timestamp: "2026-08-27T10:00:00Z", level: "ERROR", logger: "agent", message: "run failed" }),
        ].join("\n"),
      }],
      security_audit: { retention_days: 90, export_window_days: 7, max_records: 500, records: [] },
    });
  });

  afterEach(() => cleanup());

  it("filters bounded log rows, toggles wrapping, and copies one redacted row", async () => {
    render(<DiagnosticsPage onToast={onToast} />);

    expect(await screen.findByText("engine ready")).toBeTruthy();
    expect(screen.getByText("显示 3 / 3 行")).toBeTruthy();

    fireEvent.change(screen.getByRole("textbox", { name: "搜索当前日志" }), { target: { value: "timeout" } });
    expect(screen.getByText("显示 1 / 3 行")).toBeTruthy();
    expect(screen.queryByText("engine ready")).toBeNull();
    expect(screen.getByText("connection timeout")).toBeTruthy();

    fireEvent.click(screen.getByRole("switch", { name: "自动换行" }));
    expect(screen.getByRole("table", { name: "后端日志内容" }).classList.contains("diagnostics-log-list--wrap")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /复制日志行/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining("connection timeout")));
    expect(onToast).toHaveBeenCalledWith("日志行已复制", "success");
  });

  it("keeps a load failure on the diagnostics surface and exposes only safe correlation metadata", async () => {
    getLogsMock.mockRejectedValueOnce(new ApiError(
      "private backend failure",
      503,
      "DIAGNOSTICS_UNAVAILABLE",
      [],
      { request_id: "diag-request-7", secret: "must-not-render" },
    ));

    render(<DiagnosticsPage onToast={onToast} />);

    expect((await screen.findByRole("alert")).textContent).toContain("诊断日志加载失败");
    expect(onToast).not.toHaveBeenCalledWith(expect.any(String), "error");
    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText("DIAGNOSTICS_UNAVAILABLE")).toBeTruthy();
    expect(screen.getByText("diag-request-7")).toBeTruthy();
    expect(document.body.textContent).not.toContain("private backend failure");
    expect(document.body.textContent).not.toContain("must-not-render");
  });

  it("keeps a clear failure inline instead of duplicating it in a toast", async () => {
    clearLogsMock.mockRejectedValueOnce(new ApiError(
      "private log path",
      503,
      "DIAGNOSTICS_CLEAR_FAILED",
      [],
      { request_id: "diag-clear-2", secret: "must-not-render" },
    ));
    render(<DiagnosticsPage onToast={onToast} />);
    await screen.findByText("engine ready");

    fireEvent.pointerDown(screen.getByRole("button", { name: "更多诊断操作" }), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "清空日志" }));

    expect(await screen.findByText("清空日志失败")).toBeTruthy();
    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText("DIAGNOSTICS_CLEAR_FAILED")).toBeTruthy();
    expect(screen.getByText("diag-clear-2")).toBeTruthy();
    expect(document.body.textContent).not.toContain("private log path");
    expect(document.body.textContent).not.toContain("must-not-render");
    expect(onToast).not.toHaveBeenCalledWith(expect.any(String), "error");
  });
});
