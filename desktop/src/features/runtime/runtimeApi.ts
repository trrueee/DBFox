import { engineRequest } from "../engine/engineClient";

export interface RuntimeRunRequest {
  datasource_id: string;
  question: string;
  session_id?: string | null;
  parent_run_id?: string | null;
  workspace_context?: RuntimeWorkspaceContext | null;
}

export interface RuntimeWorkspaceContext {
  datasource_id: string;
  active_sql?: string | null;
  selected_table_ids?: string[];
  selected_table_names?: string[];
}

export interface RuntimeRunResponse {
  run_id: string;
  session_id: string;
  success: boolean;
  question: string;
}

export function runRuntime(request: RuntimeRunRequest) {
  const path = "/agent" + "/run";
  return engineRequest<RuntimeRunResponse>(path, {
    method: "POST",
    body: JSON.stringify(request),
  });
}
