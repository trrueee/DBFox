import type {
  ChartDataResponse,
  ConsoleExecuteRequest,
  ConsoleExecuteResponse,
  GuardrailResponse,
  ResultExportRequest,
  ResultFilter,
  ResultPageRequest,
  ResultPageResponse,
  ResultSort,
  TableResultExportRequest,
  TableResultPageRequest,
} from "../generated/types.gen";

export type {
  ChartDataResponse,
  ConsoleExecuteRequest,
  ConsoleExecuteResponse,
  ResultExportRequest,
  ResultFilter,
  ResultPageRequest,
  ResultPageResponse,
  ResultSort,
  TableResultExportRequest,
  TableResultPageRequest,
};

export type GuardrailCheckResult = GuardrailResponse;
export type ResultFilterOperator = ResultFilter["operator"];
