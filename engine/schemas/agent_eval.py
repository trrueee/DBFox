from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentGoldenTaskCreateRequest(BaseModel):
    datasource_id: str
    project_id: str | None = None
    name: str
    description: str | None = None
    question: str
    workspace_context_json: str = "{}"
    expected_intent: str | None = None
    expected_tools_json: str = "[]"
    forbidden_tools_json: str = "[]"
    expected_artifact_types_json: str = "[]"
    expected_final_contains_json: str = "[]"
    expected_approval_state: str | None = None
    expected_sql_required: bool = False
    tags_json: str = "[]"
    source: str = "internal"
    source_case_id: str | None = None
    difficulty: str | None = None


class AgentGoldenTaskUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    question: str | None = None
    workspace_context_json: str | None = None
    expected_intent: str | None = None
    expected_tools_json: str | None = None
    forbidden_tools_json: str | None = None
    expected_artifact_types_json: str | None = None
    expected_final_contains_json: str | None = None
    expected_approval_state: str | None = None
    expected_sql_required: bool | None = None
    tags_json: str | None = None
    difficulty: str | None = None


class AgentGoldenTaskResponse(BaseModel):
    id: str
    datasource_id: str
    project_id: str | None = None
    name: str
    description: str | None = None
    question: str
    workspace_context_json: str
    expected_intent: str | None = None
    expected_tools_json: str
    forbidden_tools_json: str
    expected_artifact_types_json: str
    expected_final_contains_json: str
    expected_approval_state: str | None = None
    expected_sql_required: bool
    tags_json: str
    source: str
    source_case_id: str | None = None
    difficulty: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}


class AgentEvalRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasource_id: str
    project_id: str | None = None
    task_ids: list[str] | None = None
    tags: list[str] | None = None
    source: str | None = None
    llm_credential_id: str
    api_base: str | None = None
    model_name: str | None = None
    execute: bool = False


class AgentEvalRunResponse(BaseModel):
    id: str
    datasource_id: str
    project_id: str | None = None
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float | None = None
    avg_latency_ms: float | None = None
    summary_json: str
    created_at: str | None = None
    completed_at: str | None = None
    case_results: list[AgentEvalCaseResultResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AgentEvalCaseResultResponse(BaseModel):
    id: str
    eval_run_id: str
    task_id: str
    run_id: str | None = None
    status: str
    score: float
    latency_ms: int | None = None
    actual_intent: str | None = None
    actual_tools_json: str
    actual_artifact_types_json: str
    actual_approval_state: str | None = None
    actual_sql_json: str
    failure_reasons_json: str
    response_json: str
    created_at: str | None = None

    model_config = {"from_attributes": True}


class AgentBenchmarkImportRequest(BaseModel):
    datasource_id: str
    project_id: str | None = None
    source: str = "internal"
    file_path: str | None = None
    payload: dict[str, Any] | None = None
    limit: int | None = None


class AgentBenchmarkImportResponse(BaseModel):
    source: str
    total_imported: int
    task_ids: list[str] = Field(default_factory=list)
