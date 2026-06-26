import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationSummary } from "../../../types/conversation";
import { ConversationHistoryPanel } from "../ConversationHistoryPanel";

const conversations: ConversationSummary[] = [
  {
    id: "conv-1",
    title: "统计订单趋势",
    datasource_id: "ds-1",
    updated_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    last_message: "请统计最近一周的订单趋势",
    message_count: 3,
    run_status: "completed",
    artifact_count: 2,
  },
  {
    id: "conv-2",
    title: "客户分层",
    datasource_id: "ds-1",
    updated_at: "not-a-date",
    last_message: "",
    message_count: 1,
    run_status: "failed",
    artifact_count: 0,
  },
];

describe("ConversationHistoryPanel", () => {
  beforeEach(() => {
    cleanup();
  });

  it("renders conversation count and opens a selected conversation", () => {
    const onOpenConversation = vi.fn();
    render(
      <ConversationHistoryPanel
        conversations={conversations}
        activeConversationId="conv-1"
        onOpenConversation={onOpenConversation}
        onDeleteConversation={vi.fn()}
      />,
    );

    expect(screen.getByText("2 条")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "打开 统计订单趋势" }));

    expect(onOpenConversation).toHaveBeenCalledWith(conversations[0]);
  });

  it("deletes a conversation without opening it", () => {
    const onOpenConversation = vi.fn();
    const onDeleteConversation = vi.fn();
    render(
      <ConversationHistoryPanel
        conversations={conversations}
        onOpenConversation={onOpenConversation}
        onDeleteConversation={onDeleteConversation}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "删除 统计订单趋势" }));

    expect(onDeleteConversation).toHaveBeenCalledWith("conv-1");
    expect(onOpenConversation).not.toHaveBeenCalled();
  });

  it("shows a shared empty state when no conversations exist", () => {
    render(
      <ConversationHistoryPanel
        conversations={[]}
        onOpenConversation={vi.fn()}
        onDeleteConversation={vi.fn()}
      />,
    );

    expect(screen.getByText("暂无历史记录")).toBeTruthy();
    expect(screen.getByText("提交问数后，会话会自动保存。")).toBeTruthy();
  });
});
