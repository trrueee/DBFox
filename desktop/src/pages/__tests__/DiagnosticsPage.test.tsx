import { fireEvent, render, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DiagnosticsPage } from "../DiagnosticsPage";
import { diagnosticsApi } from "../../lib/api/diagnostics";

vi.mock("../../lib/api/diagnostics", () => ({
  diagnosticsApi: {
    getLogs: vi.fn(),
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
      ],
    });
  });

  it("renders sanitized diagnostic logs and copies a diagnostic bundle", async () => {
    const onToast = vi.fn();
    const { getByRole, getByText, queryByText } = render(<DiagnosticsPage onToast={onToast} />);

    await waitFor(() => expect(diagnosticsApi.getLogs).toHaveBeenCalled());

    expect(getByText("诊断日志")).toBeInTheDocument();
    expect(getByText("已脱敏")).toBeInTheDocument();
    expect(getByText("engine")).toBeInTheDocument();
    expect(getByText(/api_key=\[REDACTED\]/)).toBeInTheDocument();
    expect(queryByText("secret-key")).not.toBeInTheDocument();

    fireEvent.click(getByRole("button", { name: "复制诊断包" }));

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledOnce());
    expect(onToast).toHaveBeenCalledWith("诊断包已复制", "success");
  });
});
