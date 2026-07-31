import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConversationDetail } from "../../../../types/conversation";
import { ConversationHeader } from "../ConversationHeader";

const detail: ConversationDetail = {
  protocol_version: 2,
  id: "conversation-debug-identifier",
  title: "分析最近一周的订单趋势",
  datasource_id: "datasource-1",
  context_tables: [],
  runs: [],
  items: [],
};

describe("ConversationHeader", () => {
  afterEach(cleanup);

  it("presents the full conversation title without redundant branding or internal ids", () => {
    render(
      <ConversationHeader detail={detail} onOpenHistory={vi.fn()} onDelete={vi.fn()} />,
    );

    expect(screen.getByRole("heading", { name: detail.title })).toBeTruthy();
    expect(screen.queryByText("DBFox Agent")).toBeNull();
    expect(screen.queryByText(/conversation-debug-identifier/)).toBeNull();
  });

  it("keeps history and delete as accessible actions", () => {
    const onOpenHistory = vi.fn();
    const onDelete = vi.fn();
    render(
      <ConversationHeader
        detail={detail}
        onOpenHistory={onOpenHistory}
        onDelete={onDelete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "打开对话历史" }));
    fireEvent.click(screen.getByRole("button", { name: "删除当前对话" }));

    expect(onOpenHistory).toHaveBeenCalledOnce();
    expect(onDelete).toHaveBeenCalledOnce();
  });
});
