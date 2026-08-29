import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ApprovalItem,
  AssistantMessageItem,
  ConversationArtifact,
  ConversationDetail,
  ConversationRun,
  ConversationRunItem,
  PlanItem,
} from "../../../../types/conversation";
import { ConversationWorkspace } from "../ConversationWorkspace";

const viewModel = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
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
    Object.defineProperty(window, "ResizeObserver", {
      configurable: true,
      value: ResizeObserverMock,
    });
    HTMLElement.prototype.scrollTo = vi.fn();
    window.localStorage.clear();
    cleanup();
    viewModel.current = {
      detail: detail(),
      items: [] as ConversationRunItem[],
      runs: [] as ConversationRun[],
      artifacts: artifacts(),
      runningRun: null,
      openConversation: vi.fn(),
      streamState: "idle",
      streamError: null,
      sendMessage: vi.fn(),
      cancelRun: vi.fn(),
      resolveApproval: vi.fn(),
      resolveQuestion: vi.fn(),
      selectArtifact: vi.fn(),
      loadRunArtifacts: vi.fn().mockResolvedValue(undefined),
    };
  });

  it("keeps Conversation as the only Main Surface and does not render an internal ArtifactDock", () => {
    renderWorkspace();
    expect(screen.getByRole("region", { name: "Conversation" })).toBeTruthy();
    expect(screen.queryByRole("complementary", { name: "Artifact dock" })).toBeNull();
    expect(screen.queryByRole("separator", { name: "调整工件区宽度" })).toBeNull();
  });

  it("pins the canonical waiting approval above the composer", () => {
    const runningRun = run("waiting_approval");
    const approval = approvalItem();
    viewModel.current = {
      ...viewModel.current,
      runs: [runningRun],
      runningRun,
      items: [approval],
    };
    renderWorkspace();
    const card = screen.getByRole("alert", { name: "需要批准" });
    expect(card.closest(".conv-pinned-action")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "批准执行" }));
    expect(viewModel.current.resolveApproval as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
      "run-approval",
      "approval-1",
      true,
    );
  });

  it("shows reconnecting content as stale without turning the run into a failure", () => {
    viewModel.current = {
      ...viewModel.current,
      streamState: "reconnecting",
    };

    renderWorkspace();

    expect(screen.getByRole("status")).toHaveTextContent("正在恢复实时连接");
    expect(screen.getByText(/不会重放写操作/)).toBeInTheDocument();
    expect(screen.queryByText("实时连接已中断")).toBeNull();
  });

  it("explains cursor recovery without presenting a run failure", () => {
    viewModel.current = {
      ...viewModel.current,
      streamState: "recovering_snapshot",
    };

    renderWorkspace();

    expect(screen.getByRole("status")).toHaveTextContent("正在读取最新状态");
    expect(screen.getByText(/历史游标已失效/)).toBeInTheDocument();
    expect(screen.queryByText("实时连接已中断")).toBeNull();
  });

  it("confirms when the durable snapshot has restored current content", () => {
    viewModel.current = {
      ...viewModel.current,
      streamState: "recovered",
    };

    renderWorkspace();

    expect(screen.getByRole("status")).toHaveTextContent("已恢复最新状态");
    expect(screen.getByText(/耐久快照同步/)).toBeInTheDocument();
  });

  it("offers a snapshot refresh after a terminal stream failure", () => {
    viewModel.current = {
      ...viewModel.current,
      streamState: "failed",
      streamError: "实时流协议无法识别。",
    };

    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "刷新最新状态" }));

    expect(screen.getByRole("alert")).toHaveTextContent("实时连接已中断");
    expect(viewModel.current.openConversation as ReturnType<typeof vi.fn>).toHaveBeenCalledWith("session-1");
  });

  it("loads newly referenced artifacts and reveals a result artifact selected from a citation", async () => {
    const completedRun = run("completed");
    const answer = answerItem();
    viewModel.current = {
      ...viewModel.current,
      detail: { ...detail(), selected_artifact_id: null },
      items: [answer],
      runs: [completedRun],
      artifacts: [],
    };
    const rendered = renderWorkspace();

    await waitFor(() => {
      expect(viewModel.current.loadRunArtifacts as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
        "session-1",
        completedRun.id,
        ["result-1"],
      );
    });
    fireEvent.click(screen.getByRole("button", { name: "查看证据：查询结果" }));
    expect(viewModel.current.selectArtifact as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
      "session-1",
      "result-1",
    );

    viewModel.current = {
      ...viewModel.current,
      detail: { ...detail(), selected_artifact_id: "result-1" },
      artifacts: artifacts(),
    };
    rendered.rerender(workspace());
    expect(screen.queryByRole("complementary", { name: "Artifact dock" })).toBeNull();
    expect(viewModel.current.selectArtifact as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
      "session-1",
      "result-1",
    );
  });

  it("loads artifacts referenced only by a Plan completion step", async () => {
    const completedRun = run("completed");
    const plan: PlanItem = {
      id: "plan-1",
      type: "plan",
      session_id: "session-1",
      run_id: completedRun.id,
      turn_id: "turn-1",
      sequence: 1,
      revision: 1,
      status: "completed",
      created_at: "2026-08-27T00:00:00Z",
      payload: {
        objective: "核对订单异常",
        steps: [{
          id: "step-1",
          title: "核对查询结果",
          status: "completed",
          evidence_required: true,
          artifact_ids: ["plan-result-1"],
        }],
      },
    };
    viewModel.current = {
      ...viewModel.current,
      items: [plan],
      runs: [completedRun],
      artifacts: [],
    };

    renderWorkspace();

    await waitFor(() => {
      expect(viewModel.current.loadRunArtifacts as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
        "session-1",
        completedRun.id,
        ["plan-result-1"],
      );
    });
  });
});

function renderWorkspace() {
  return render(workspace());
}

function workspace() {
  return (
    <ConversationWorkspace
      conversationId="session-1"
      onOpenSqlConsole={vi.fn()}
    />
  );
}

function detail(): ConversationDetail {
  return {
    protocol_version: 2,
    id: "session-1",
    title: "Revenue investigation",
    project_id: "project-1",
    resource_intents: [],
    runs: [],
    items: [],
    selected_artifact_id: "result-1",
    cursor: 0,
  };
}

function run(status: ConversationRun["status"]): ConversationRun {
  return {
    id: "run-approval",
    session_id: "session-1",
    input_id: "input-1",
    session_sequence: 1,
    user_message_id: "user-1",
    question: "执行查询",
    status,
    version: 1,
    cancel_requested: false,
    result: {},
    error: null,
  };
}

function approvalItem(): ApprovalItem {
  return {
    id: "approval-1",
    type: "approval",
    session_id: "session-1",
    run_id: "run-approval",
    turn_id: "turn-1",
    sequence: 2,
    revision: 1,
    status: "waiting",
    created_at: "2026-07-26T00:00:00Z",
    payload: {
      version: 0,
      risk_level: "warning",
      reason: "需要确认本次只读查询",
      requested_action: { sql: "SELECT 1" },
    },
  };
}

function answerItem(): AssistantMessageItem {
  return {
    id: "message-1",
    type: "message",
    session_id: "session-1",
    run_id: "run-approval",
    turn_id: "turn-1",
    sequence: 3,
    revision: 1,
    status: "completed",
    created_at: "2026-07-26T00:00:00Z",
    completed_at: "2026-07-26T00:00:01Z",
    payload: {
      role: "assistant",
      phase: "final_answer",
      content: "查询得到结果。",
      evidence: [{
        id: "evidence-1",
        claim_id: "claim-1",
        artifact_id: "result-1",
        label: "查询结果",
        observed_at: "2026-07-26T00:00:00Z",
        locator: {},
      }],
      artifact_refs: [{ artifact_id: "result-1", label: "查询结果" }],
      completion_disposition: "complete",
      limitation_codes: [],
    },
  };
}

function artifacts(): ConversationArtifact[] {
  return [
    {
      id: "sql-1",
      session_id: "session-1",
      run_id: "run-1",
      semantic_key: "sql",
      version: 1,
      type: "dbfox.data.sql",
      title: "Revenue SQL",
      status: "completed",
      visibility: "supporting",
      payload: {
        sql: "SELECT revenue FROM orders",
        safeSql: "SELECT revenue FROM orders",
        dialect: "sqlite",
        queryFingerprint: "sql-revenue",
      },
      provenance: {},
      relations: [],
    },
    {
      id: "result-1",
      session_id: "session-1",
      run_id: "run-1",
      semantic_key: "result",
      version: 1,
      type: "dbfox.data.result_view",
      title: "Revenue Result",
      status: "completed",
      visibility: "primary",
      payload: {
        sourceSqlArtifactId: "sql-1",
        queryFingerprint: "query-revenue",
        datasourceGeneration: 1,
        columns: ["revenue"],
        rowCount: 1,
        returnedRows: 1,
        latencyMs: 1,
        executedAt: "2026-07-26T00:00:00Z",
        truncated: false,
      },
      provenance: {},
      relations: [{ relation: "executed_as", artifact_id: "sql-1" }],
    },
  ];
}
