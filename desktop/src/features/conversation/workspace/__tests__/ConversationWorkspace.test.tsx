import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact, ConversationDetail, ConversationMessage, ConversationRun } from "../../../../types/conversation";
import { ConversationWorkspace } from "../ConversationWorkspace";

const viewModel = vi.hoisted(() => ({
  current: {
    detail: null as ConversationDetail | null,
    messages: [] as ConversationMessage[],
    runs: [] as ConversationRun[],
    artifacts: [] as ConversationArtifact[],
    runningRun: null as ConversationRun | null,
    openConversation: vi.fn(),
    sendMessage: vi.fn(),
    cancelRun: vi.fn(),
    resolveApproval: vi.fn(),
    selectArtifact: vi.fn(),
  },
}));

vi.mock("../useConversationViewModel", () => ({
  useConversationViewModel: () => viewModel.current,
}));

describe("ConversationWorkspace", () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
    Object.defineProperty(window, "ResizeObserver", { configurable: true, value: ResizeObserverMock });
    HTMLElement.prototype.scrollTo = vi.fn();
    window.localStorage.clear();
    cleanup();
    viewModel.current = {
      detail: conversationDetail(),
      messages: conversationMessages(),
      runs: [],
      artifacts: conversationArtifacts(),
      runningRun: null,
      openConversation: vi.fn(),
      sendMessage: vi.fn(),
      cancelRun: vi.fn(),
      resolveApproval: vi.fn(),
      selectArtifact: vi.fn(),
    };
  });

  it("keeps the conversation header inside the left pane and makes artifact nav the right pane top content", () => {
    const onOpenSqlConsole = vi.fn();
    render(
      <ConversationWorkspace
        conversationId="conv-1"
        onOpenHistory={vi.fn()}
        onOpenSqlConsole={onOpenSqlConsole}
        onOpenResultTab={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const conversationPane = screen.getByRole("region", { name: "Conversation" });
    const artifactDock = screen.getByRole("complementary", { name: "Artifact dock" });

    expect(screen.getByRole("heading", { name: "Revenue investigation" }).closest(".conv-conversation-pane")).toBe(
      conversationPane,
    );
    expect(conversationPane.closest(".conv-artifact-main-panel")).toBeTruthy();
    expect(artifactDock.closest(".conv-artifact-dock-panel")).toBeTruthy();
    expect(artifactDock.closest(".conv-artifact-panel-group")).toBeTruthy();
    expect(screen.getByRole("separator", { name: "调整工件区宽度" }).classList.contains("conv-artifact-resizer")).toBe(
      true,
    );
    expect(screen.getByText("会话 conv-1").closest(".conv-conversation-pane")).toBe(conversationPane);
    expect(artifactDock.querySelector(".conv-artifact-dock-header")).toBeTruthy();
    expect(screen.getByRole("button", { name: "收起工件区" })).toBeTruthy();
    expect(screen.queryByText("产物")).toBeNull();
    expect(screen.queryByText("2 items")).toBeNull();
    expect(artifactDock.querySelector(".conv-artifact-dock-list")).toBeTruthy();
    expect(artifactDock.querySelector(".conv-artifact-dock-preview")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Revenue Result Result" }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Revenue SQL SQL" }));

    expect(viewModel.current.selectArtifact).toHaveBeenCalledWith("conv-1", "sql-1");
    expect(onOpenSqlConsole).not.toHaveBeenCalled();
  });

  it("pins a pending approval directly above the composer", () => {
    viewModel.current.runningRun = {
      id: "run-approval", conversation_id: "conv-1", datasource_id: "warehouse",
      question: "执行查询", assistant_message_id: "message-1", status: "waiting_approval",
      approval: {
        id: "approval-1", run_id: "run-approval", session_id: "conv-1",
        tool_name: "sql.execute_readonly", status: "pending", risk_level: "warning",
        reason: "需要确认本次只读查询", requested_action: { sql: "SELECT 1" },
      },
    };
    render(
      <ConversationWorkspace
        conversationId="conv-1" onOpenHistory={vi.fn()} onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()} onDelete={vi.fn()}
      />,
    );

    const card = screen.getByRole("region", { name: "需要批准" });
    expect(card.closest(".conv-pinned-action")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "批准执行" }));
    expect(viewModel.current.resolveApproval).toHaveBeenCalledWith("run-approval", "approval-1", true);
  });
});

function conversationDetail(): ConversationDetail {
  const messages = conversationMessages();
  const artifacts = conversationArtifacts();
  return {
    id: "conv-1",
    title: "Revenue investigation",
    datasource_id: "warehouse",
    context_tables: [],
    created_at: null,
    updated_at: null,
    messages,
    runs: [],
    artifacts,
    approvals: [],
    selected_artifact_id: "result-1",
  };
}

function conversationMessages(): ConversationMessage[] {
  return [
    {
      id: "message-1",
      conversation_id: "conv-1",
      role: "assistant",
      content: "I found the revenue trend.",
      status: "completed",
      sequence: 1,
      created_at: null,
      updated_at: null,
    },
  ];
}

function conversationArtifacts(): ConversationArtifact[] {
  return [
    {
      id: "sql-1",
      semantic_id: "sql_candidate",
      conversation_id: "conv-1",
      run_id: "run-1",
      message_id: "message-1",
      type: "sql",
      title: "Revenue SQL",
      status: "completed",
      sequence: 1,
      payload: { sql: "SELECT revenue FROM orders" },
      depends_on: [],
    },
    {
      id: "result-1",
      semantic_id: "result_view_1",
      conversation_id: "conv-1",
      run_id: "run-1",
      message_id: "message-1",
      type: "result_view",
      title: "Revenue Result",
      status: "completed",
      sequence: 2,
      payload: {
        sourceSqlArtifactId: "sql-1",
        queryFingerprint: "query-revenue",
        datasourceGeneration: 1,
        columns: ["revenue"],
        rowCount: 1,
        returnedRows: 1,
        latencyMs: 1,
        executedAt: "2026-07-19T00:00:00Z",
        truncated: false,
      },
      depends_on: ["sql_candidate"],
    },
  ];
}
