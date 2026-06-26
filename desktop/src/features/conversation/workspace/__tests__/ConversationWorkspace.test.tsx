import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact, ConversationDetail, ConversationMessage } from "../../../../types/conversation";
import { ConversationWorkspace } from "../ConversationWorkspace";

const viewModel = vi.hoisted(() => ({
  current: {
    detail: null as ConversationDetail | null,
    messages: [] as ConversationMessage[],
    runs: [],
    artifacts: [] as ConversationArtifact[],
    runningRun: null,
    openConversation: vi.fn(),
    sendMessage: vi.fn(),
    cancelRun: vi.fn(),
    resolveApproval: vi.fn(),
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
    expect(artifactDock.querySelector(".conv-artifact-dock-header")).toBeNull();
    expect(screen.queryByText("产物")).toBeNull();
    expect(screen.queryByText("2 items")).toBeNull();
    expect(artifactDock.querySelector(".conv-artifact-dock-list")).toBeTruthy();
    expect(artifactDock.querySelector(".conv-artifact-dock-preview")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Revenue Result Result" }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByText("SQL: Revenue SQL"));

    expect(screen.getByRole("button", { name: "Revenue SQL SQL" }).getAttribute("aria-pressed")).toBe("true");
    expect(onOpenSqlConsole).not.toHaveBeenCalled();
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
        storageMode: "sql_backed",
        datasourceId: "ds-1",
        sourceSqlArtifactId: "sql-1",
        safeSql: "SELECT revenue FROM orders",
        columns: ["revenue"],
        previewRows: [["42"]],
        rowCount: 1,
      },
      depends_on: ["sql_candidate"],
    },
  ];
}
