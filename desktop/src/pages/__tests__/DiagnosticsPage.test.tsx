import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DiagnosticsPage } from "../DiagnosticsPage";
import { diagnosticsApi } from "../../lib/api/diagnostics";

vi.mock("../../lib/api/diagnostics", () => ({
  diagnosticsApi: {
    getLogs: vi.fn(),
    clearLogs: vi.fn(),
    clearSecurityAudit: vi.fn(),
  },
}));

describe("DiagnosticsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    vi.mocked(diagnosticsApi.getLogs).mockResolvedValue({
      generated_at: "2026-06-20T00:00:00Z",
      policy: {
        redacted: true,
        max_lines_per_source: 300,
        omitted: ["API keys"],
      },
      environment: {
        app: "DBFox",
        pid: 123,
        python: "3.12.0",
        platform: "Windows",
        frozen: false,
      },
      sources: [
        {
          name: "engine",
          path: "C:/Users/Lenovo/AppData/Roaming/DBFox/logs/dbfox-engine.log",
          exists: true,
          size_bytes: 42,
          modified_at: "2026-06-20T00:00:00Z",
          content: "ERROR api_key=[REDACTED] failed",
        },
        {
          name: "engine-stderr",
          path: "artifacts/runtime-logs/engine.err.log",
          exists: true,
          size_bytes: 20,
          modified_at: "2026-06-20T00:00:01Z",
          content: "backend stderr",
        },
        {
          name: "frontend-stdout",
          path: "artifacts/runtime-logs/frontend.out.log",
          exists: true,
          size_bytes: 18,
          modified_at: "2026-06-20T00:00:02Z",
          content: "frontend stdout",
        },
      ],
      security_audit: {
        retention_days: 90,
        export_window_days: 7,
        max_records: 500,
        records: [],
      },
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("uses embedded chrome without a duplicate page title", async () => {
    const { getByRole, queryByRole } = render(<DiagnosticsPage onToast={vi.fn()} chrome="workspace" />);

    await waitFor(() => expect(diagnosticsApi.getLogs).toHaveBeenCalled());

    expect(queryByRole("heading", { name: "诊断日志" })).not.toBeInTheDocument();
    expect(getByRole("button", { name: "刷新" })).toBeInTheDocument();
    expect(getByRole("button", { name: "复制诊断包" })).toBeInTheDocument();
    expect(getByRole("button", { name: "清空审计" })).toBeInTheDocument();
    expect(getByRole("switch", { name: "显示空日志" })).toBeInTheDocument();
  });

  it("renders sanitized diagnostic logs and copies a diagnostic bundle", async () => {
    const onToast = vi.fn();
    const { getByRole, getByText, queryByText } = render(<DiagnosticsPage onToast={onToast} />);

    await waitFor(() => expect(diagnosticsApi.getLogs).toHaveBeenCalled());

    expect(getByText("诊断日志")).toBeInTheDocument();
    expect(getByText("已脱敏")).toBeInTheDocument();
    expect(getByRole("heading", { name: "后端日志" })).toBeInTheDocument();
    expect(getByText("engine, engine-stderr")).toBeInTheDocument();
    expect(getByText(/api_key=\[REDACTED\]/)).toBeInTheDocument();
    expect(getByText(/backend stderr/)).toBeInTheDocument();
    expect(queryByText("secret-key")).not.toBeInTheDocument();

    fireEvent.click(getByRole("button", { name: "复制诊断包" }));

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledOnce());
    expect(onToast).toHaveBeenCalledWith("诊断包已复制", "success");
  });

  it("switches between backend and frontend diagnostic groups from a scrollable dropdown", async () => {
    const { getByRole, getByText, queryByText } = render(<DiagnosticsPage onToast={vi.fn()} />);

    await waitFor(() => expect(diagnosticsApi.getLogs).toHaveBeenCalled());

    const selector = getByRole("button", { name: "日志分组" });
    expect(selector).toHaveClass("diagnostics-source-trigger");
    expect(selector).toHaveAttribute("aria-expanded", "false");
    expect(getByRole("heading", { name: "后端日志" })).toBeInTheDocument();
    expect(queryByText(/frontend stdout/)).not.toBeInTheDocument();

    fireEvent.click(selector);
    expect(selector).toHaveAttribute("aria-expanded", "true");
    const menu = getByRole("listbox", { name: "日志分组" });
    expect(menu).toHaveClass("diagnostics-source-menu");

    fireEvent.click(getByRole("option", { name: /前端日志/ }));

    expect(getByRole("heading", { name: "前端日志" })).toBeInTheDocument();
    expect(getByText("frontend-stdout, frontend-client")).toBeInTheDocument();
    expect(getByText(/frontend stdout/)).toBeInTheDocument();
    expect(queryByText(/backend stderr/)).not.toBeInTheDocument();
  });
});
