import type {
  BackupResponse,
  ConfirmationRequiredResponse,
  DataSourceCreateRequest,
  DataSourceHealthResponse,
  DataSourceResponse,
  DatasourceDeleteConfirmRequest,
  DataSourceTestRequest,
  DataSourceTestResponse,
  DataSourceUpdateRequest,
  ProjectResponse,
  SchemaAiEnrichResponse,
  SchemaColumnResponse,
  SchemaSyncRequest,
  SchemaSyncResponse,
  SchemaTableResponse,
} from "../generated/types.gen";

export type ConfirmationRequired = ConfirmationRequiredResponse;
export type DangerousOperationResult<T> = T | ConfirmationRequired;
export type DataSource = DataSourceResponse;
export type DataSourceTestParams = DataSourceTestRequest;
export type DataSourceCreateParams = DataSourceCreateRequest;
export type DataSourceUpdateParams = DataSourceUpdateRequest;
export type DeleteConfirm = DatasourceDeleteConfirmRequest;
export type SchemaSyncOptions = SchemaSyncRequest;
export type SchemaAiEnrichResult = SchemaAiEnrichResponse;
export type DataSourceHealthResult = DataSourceHealthResponse;
export type Project = ProjectResponse;
export type BackupRecord = BackupResponse;
export type SchemaTable = SchemaTableResponse;
export type SchemaColumn = SchemaColumnResponse;
export type DataSourceTestResult = DataSourceTestResponse;
export type SchemaSyncResult = SchemaSyncResponse;
