import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi } from "vitest";
import { ExecutionLogView } from "../ExecutionLogView";
import type { JobPage } from "../../../lib/api/generated/types.gen";

const running: JobPage = {
  job: {
    id: "job_00000000000000000000000000000000", run_id: "run-1", state: "running", reason: null,
    executable: "C:/Python/python.exe", argv: ["python", "-u", "server.py"], shell_script: null,
    cwd: "D:/Project", lifetime: "background", interactive: false, stdin_open: false, timeout_seconds: 300,
    root_exit_code: null, active_processes: 2, output_finalized: false,
    first_cursor: 1, last_cursor: 1, retained_bytes: 12, duration_ms: 250,
  },
  chunks: [{ cursor: 1, stream: "stdout", text: "server ready\n" }],
  next_cursor: 1, cursor_expired: false, has_more: false,
};

describe("Execution log Dock projection", () => {
  it("reads after the received cursor and only reports stop after the server reports a terminal state", async () => {
    const ended: JobPage = {
      ...running,
      job: { ...running.job, state: "cancelled", root_exit_code: 1, active_processes: 0, output_finalized: true, last_cursor: 2 },
      chunks: [{ cursor: 2, stream: "stderr", text: "process ended\n" }],
      next_cursor: 2,
    };
    let requested = false;
    const read = vi.fn(async () => requested ? ended : running);
    const stop = vi.fn(async () => { requested = true; });
    render(<ExecutionLogView read={read} stop={stop} />);

    expect(await screen.findByText("server ready")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /^停止$/ }));
    expect(stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "已请求停止" })).toBeDisabled();
    expect(await screen.findByText("process ended")).toBeVisible();
    expect(screen.getByText(/已停止 · 退出码 1/)).toBeVisible();
    expect(read).toHaveBeenNthCalledWith(2, 1, false, expect.any(AbortSignal));
  });

  it("recovers a failed read and aborts requests when the Dock unmounts", async () => {
    const read = vi.fn()
      .mockRejectedValueOnce(new Error("暂时不可用"))
      .mockResolvedValueOnce(running)
      .mockResolvedValue({ ...running, chunks: [] });
    const { unmount } = render(<ExecutionLogView read={read} />);
    fireEvent.click(await screen.findByRole("button", { name: "重试" }));
    await waitFor(() => expect(screen.getByText("server ready")).toBeVisible());
    const requestSignal: AbortSignal = read.mock.lastCall?.[2];
    unmount();
    expect(requestSignal.aborted).toBe(true);
  });
});
