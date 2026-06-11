import { request } from "./client";

// Mirrors engine/schemas/agent_eval.py

export interface AgentGoldenTask {
  id: string;
  datasource_id: string;
  project_id?: string | null;
  name: string;
  description?: string | null;
  question: string;
  workspace_context_json: string;
  expected_intent?: string | null;
  expected_tools_json: string;
  forbidden_tools_json: string;
  expected_artifact_types_json: string;
  expected_final_contains_json: string;
  expected_approval_state?: string | null;
  expected_sql_required: boolean;
  tags_json: string;
  source: string;
  source_case_id?: string | null;
  difficulty?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AgentGoldenTaskCreatePayload {
  datasource_id: string;
  name: string;
  question: string;
  description?: string;
  expected_intent?: string;
  expected_artifact_types_json?: string;
  expected_final_contains_json?: string;
  expected_sql_required?: boolean;
  tags_json?: string;
  difficulty?: string;
}

export interface AgentEvalCaseResult {
  id: string;
  eval_run_id: string;
  task_id: string;
  run_id?: string | null;
  status: string;
  score: number;
  latency_ms?: number | null;
  actual_intent?: string | null;
  actual_tools_json: string;
  actual_artifact_types_json: string;
  actual_approval_state?: string | null;
  actual_sql_json: string;
  failure_reasons_json: string;
  response_json: string;
  created_at?: string | null;
}

export interface AgentEvalRun {
  id: string;
  datasource_id: string;
  project_id?: string | null;
  status: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  pass_rate?: number | null;
  avg_latency_ms?: number | null;
  summary_json: string;
  created_at?: string | null;
  completed_at?: string | null;
  case_results?: AgentEvalCaseResult[];
}

export interface AgentEvalRunPayload {
  datasource_id: string;
  task_ids?: string[];
  tags?: string[];
  source?: string;
  api_key?: string;
  api_base?: string;
  model_name?: string;
  execute?: boolean;
}

export const agentEvalApi = {
  listTasks: (datasourceId: string) =>
    request<AgentGoldenTask[]>(`/agent-eval/tasks?datasource_id=${encodeURIComponent(datasourceId)}`),

  createTask: (payload: AgentGoldenTaskCreatePayload) =>
    request<AgentGoldenTask>("/agent-eval/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteTask: (taskId: string) =>
    request<{ success: boolean }>(`/agent-eval/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" }),

  runEval: (payload: AgentEvalRunPayload) =>
    request<AgentEvalRun>("/agent-eval/run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listRuns: (datasourceId: string) =>
    request<AgentEvalRun[]>(`/agent-eval/runs?datasource_id=${encodeURIComponent(datasourceId)}`),

  getRunCases: (evalRunId: string) =>
    request<AgentEvalCaseResult[]>(`/agent-eval/runs/${encodeURIComponent(evalRunId)}/cases`),
};
