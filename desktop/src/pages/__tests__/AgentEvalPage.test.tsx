import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentEvalPage } from "../AgentEvalPage";

const apiMocks = vi.hoisted(() => ({
  listTasks: vi.fn(),
  listRuns: vi.fn(),
  createTask: vi.fn(),
  deleteTask: vi.fn(),
  runEval: vi.fn(),
  getRunCases: vi.fn(),
}));

vi.mock("../../lib/api/agentEval", () => ({
  agentEvalApi: apiMocks,
}));

function goldenTask(id: string, datasourceId: string, name: string) {
  return {
    id,
    datasource_id: datasourceId,
    project_id: null,
    name,
    description: null,
    question: `${name} question`,
    workspace_context_json: "{}",
    expected_intent: null,
    expected_tools_json: "[]",
    forbidden_tools_json: "[]",
    expected_artifact_types_json: "[]",
    expected_final_contains_json: JSON.stringify(["关键字"]),
    expected_approval_state: null,
    expected_sql_required: true,
    tags_json: "[]",
    source: "manual",
    source_case_id: null,
    difficulty: null,
    created_at: null,
    updated_at: null,
  };
}

function evalRun(id: string, datasourceId: string) {
  return {
    id,
    datasource_id: datasourceId,
    project_id: null,
    status: "completed",
    total_cases: 2,
    passed_cases: 1,
    failed_cases: 1,
    pass_rate: 0.5,
    avg_latency_ms: 1200,
    summary_json: "{}",
    created_at: "2026-06-22T00:00:00Z",
    completed_at: "2026-06-22T00:01:00Z",
  };
}

describe("AgentEvalPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("loads golden tasks and eval runs for the active datasource", async () => {
    apiMocks.listTasks.mockResolvedValue([goldenTask("task-1", "ds-1", "订单统计")]);
    apiMocks.listRuns.mockResolvedValue([evalRun("run-1", "ds-1")]);

    render(
      <AgentEvalPage
        datasources={[{ id: "ds-1", name: "业务库" }]}
        activeDatasourceId="ds-1"
        onToast={vi.fn()}
      />,
    );

    expect(await screen.findByText("订单统计")).toBeTruthy();
    expect(screen.getByText("订单统计 question")).toBeTruthy();
    expect(screen.getByText("1/2 通过")).toBeTruthy();
    expect(apiMocks.listTasks).toHaveBeenCalledWith("ds-1");
    expect(apiMocks.listRuns).toHaveBeenCalledWith("ds-1");
  });

  it("replaces loaded data when the active datasource changes", async () => {
    apiMocks.listTasks.mockImplementation((datasourceId: string) => (
      Promise.resolve([goldenTask(`task-${datasourceId}`, datasourceId, `任务 ${datasourceId}`)])
    ));
    apiMocks.listRuns.mockImplementation((datasourceId: string) => (
      Promise.resolve([evalRun(`run-${datasourceId}`, datasourceId)])
    ));

    const { rerender } = render(
      <AgentEvalPage
        datasources={[{ id: "ds-1", name: "业务库" }, { id: "ds-2", name: "测试库" }]}
        activeDatasourceId="ds-1"
        onToast={vi.fn()}
      />,
    );

    expect(await screen.findByText("任务 ds-1")).toBeTruthy();

    rerender(
      <AgentEvalPage
        datasources={[{ id: "ds-1", name: "业务库" }, { id: "ds-2", name: "测试库" }]}
        activeDatasourceId="ds-2"
        onToast={vi.fn()}
      />,
    );

    expect(await screen.findByText("任务 ds-2")).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByText("任务 ds-1")).toBeNull();
    });
  });

  it("passes stored product LLM config when running evals", async () => {
    localStorage.setItem(
      "dbfox-api-config",
      JSON.stringify({
        apiKey: " sk-eval ",
        apiBase: " https://dashscope.aliyuncs.com/compatible-mode/v1 ",
        modelName: " qwen-plus ",
      }),
    );
    apiMocks.listTasks.mockResolvedValue([goldenTask("task-1", "ds-1", "订单统计")]);
    apiMocks.listRuns.mockResolvedValue([]);
    apiMocks.runEval.mockResolvedValue({
      id: "run-new",
      datasource_id: "ds-1",
      project_id: null,
      status: "completed",
      total_cases: 1,
      passed_cases: 1,
      failed_cases: 0,
      pass_rate: 1,
      avg_latency_ms: 500,
      summary_json: "{}",
      created_at: null,
      completed_at: null,
      case_results: [],
    });

    render(
      <AgentEvalPage
        datasources={[{ id: "ds-1", name: "业务库" }]}
        activeDatasourceId="ds-1"
        onToast={vi.fn()}
      />,
    );

    expect(await screen.findByText("订单统计")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /运行评测/ }));

    await waitFor(() => {
      expect(apiMocks.runEval).toHaveBeenCalledWith({
        datasource_id: "ds-1",
        api_key: "sk-eval",
        api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_name: "qwen-plus",
        execute: false,
      });
    });
  });
});
