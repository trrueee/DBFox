import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useConversationStore } from "../../../stores/conversationStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { ConversationCenter } from "../ConversationCenter";

const smartQueryProps = vi.hoisted(() => ({
  latest: null as Record<string, unknown> | null,
}));

vi.mock("../../datasource/useDatasourceState", () => ({
  useDatasourceState: () => ({
    activeDatasource: {
      id: "ds-1",
      name: "creatorhub",
      db_type: "mysql",
      status: "active",
      database_name: "creatorhub",
      connection_generation: 1,
    },
  }),
}));
vi.mock("../../workspace/SmartQueryHome", () => ({
  SmartQueryHome: (props: Record<string, unknown>) => {
    smartQueryProps.latest = props;
    return <div data-testid="smart-query-home" />;
  },
}));
vi.mock("../../conversation/workspace/ConversationWorkspace", () => ({
  ConversationWorkspace: () => (
    <div data-testid="conversation-workspace" data-main-surface="conversation" />
  ),
}));

describe("ConversationCenter", () => {
  beforeEach(() => {
    cleanup();
    smartQueryProps.latest = null;
    useWorkspaceStore.setState({
      centerMode: "home",
      pendingAsk: null,
      settingsOpen: false,
    });
    useConversationStore.setState({ activeConversationId: null });
  });

  it("renders the ask home and carries a pending ask from the dock", () => {
    useWorkspaceStore.setState({ pendingAsk: "分析最近一周注册用户" });
    render(<ConversationCenter showToast={vi.fn()} onNewProject={vi.fn()} />);

    expect(screen.getByTestId("smart-query-home")).toBeTruthy();
    expect(smartQueryProps.latest).toMatchObject({ askInputValue: "分析最近一周注册用户" });
  });

  it("renders only the conversation workspace when a conversation is active", async () => {
    useWorkspaceStore.setState({ centerMode: "conversation" });
    useConversationStore.setState({ activeConversationId: "conv-1" });
    render(<ConversationCenter showToast={vi.fn()} onNewProject={vi.fn()} />);

    expect(await screen.findByTestId("conversation-workspace")).toBeTruthy();
    expect(screen.queryByTestId("smart-query-home")).toBeNull();
    expect(screen.getByTestId("conversation-workspace").getAttribute("data-main-surface")).toBe("conversation");
  });
});
