import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
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

  it("presents only the conversation title without redundant branding or internal ids", () => {
    render(<ConversationHeader detail={detail} />);

    expect(screen.getByRole("heading", { name: detail.title })).toBeTruthy();
    expect(screen.queryByText("DBFox Agent")).toBeNull();
    expect(screen.queryByText(/conversation-debug-identifier/)).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
