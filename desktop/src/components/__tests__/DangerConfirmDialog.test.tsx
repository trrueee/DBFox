import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DangerConfirmDialog, type ConfirmationDetails } from "../DangerConfirmDialog";

function confirmationDetails(overrides: Partial<ConfirmationDetails> = {}): ConfirmationDetails {
  return {
    confirm_token: "token-1",
    impact_summary: "将删除当前数据源连接。",
    expected_confirm_text: "DELETE",
    onConfirm: vi.fn().mockResolvedValue(undefined),
    onCancel: vi.fn(),
    ...overrides,
  };
}

describe("DangerConfirmDialog", () => {
  it("resets transient input and error when the confirmation token changes", async () => {
    const onConfirm = vi.fn().mockRejectedValueOnce(new Error("确认失败"));
    const { rerender } = render(
      <DangerConfirmDialog details={confirmationDetails({ onConfirm })} />,
    );

    fireEvent.change(screen.getByPlaceholderText("DELETE"), { target: { value: "DELETE" } });
    fireEvent.click(screen.getByRole("button", { name: "确认执行" }));

    await waitFor(() => {
      expect(screen.getByText("确认失败")).toBeTruthy();
    });

    rerender(
      <DangerConfirmDialog
        details={confirmationDetails({
          confirm_token: "token-2",
          impact_summary: "将删除另一个数据源连接。",
          expected_confirm_text: "DROP",
        })}
      />,
    );

    expect((screen.getByPlaceholderText("DROP") as HTMLInputElement).value).toBe("");
    expect(screen.queryByText("确认失败")).toBeNull();
  });
});
