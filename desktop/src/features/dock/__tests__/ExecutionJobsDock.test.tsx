import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { ExecutionJobsDock } from "../ExecutionJobsDock";
import { localExecutionApi } from "../../../lib/api/localExecution";
import type { JobView } from "../../../lib/api/generated/types.gen";

vi.mock("../../../lib/api/localExecution", () => ({ localExecutionApi: { list: vi.fn() } }));

describe("Execution task list", () => {
  it("discovers a new task while the previously empty list stays open", async () => {
    const job: JobView = {
      id: "job_00000000000000000000000000000001", run_id: "run", state: "running", reason: null,
      executable: "C:/Python/python.exe", argv: ["python", "server.py"], shell_script: null,
      cwd: "D:/Project", lifetime: "background", interactive: false, stdin_open: false, timeout_seconds: 300,
      root_exit_code: null, active_processes: 1, output_finalized: false,
      first_cursor: 1, last_cursor: 0, retained_bytes: 0, duration_ms: 1,
    };
    vi.mocked(localExecutionApi.list).mockResolvedValueOnce([]).mockResolvedValue([job]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(<QueryClientProvider client={client}><ExecutionJobsDock conversationId="session" /></QueryClientProvider>);
    try {
      expect(await screen.findByText("暂无本机任务")).toBeTruthy();
      expect(await screen.findByRole("button", { name: /python server.py/ }, { timeout: 2500 })).toBeTruthy();
      expect(localExecutionApi.list).toHaveBeenCalledTimes(2);
    } finally {
      unmount();
      client.clear();
    }
  });
});
