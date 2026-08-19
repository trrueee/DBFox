import { DeferredChartArtifactView } from "./DeferredChartArtifactView";
import { SqlArtifactView } from "./SqlArtifactView";
import { TableArtifactView } from "./TableArtifactView";
import type {
  ArtifactRendererContribution,
} from "./types";
import { asRecord, requiredString } from "./types";
import type {
  ChartArtifact,
  ResultViewArtifact,
  SqlArtifact,
} from "../../../types/agentArtifact";

export interface DataArtifactRendererActions {
  onOpenSqlConsole?: (initialSql?: string) => void;
  onOpenResultTab?: (artifact: ResultViewArtifact) => void;
  sourceSqlArtifact?: SqlArtifact;
}

function parseResultViewPayload(value: unknown): ResultViewArtifact {
  const payload = asRecord(value);
  const columns = payload.columns;
  if (!Array.isArray(columns)) {
    throw new Error("result_view payload requires columns");
  }
  return {
    id: "",
    type: "result_view",
    schemaVersion: 1,
    title: "",
    sourceSqlArtifactId: requiredString(payload.sourceSqlArtifactId, "sourceSqlArtifactId"),
    queryFingerprint: requiredString(payload.queryFingerprint, "queryFingerprint"),
    columns: columns as ResultViewArtifact["columns"],
    datasourceGeneration:
      typeof payload.datasourceGeneration === "number"
        ? payload.datasourceGeneration
        : undefined,
    rowCount:
      typeof payload.rowCount === "number" ? payload.rowCount : undefined,
    returnedRows:
      typeof payload.returnedRows === "number" ? payload.returnedRows : undefined,
    latencyMs:
      typeof payload.latencyMs === "number" ? payload.latencyMs : undefined,
    truncated: payload.truncated === true,
  };
}

function parseChartPayload(value: unknown): ChartArtifact {
  const payload = asRecord(value);
  const chartType = requiredString(payload.chartType, "chartType");
  if (!["line", "bar", "pie", "scatter", "area"].includes(chartType)) {
    throw new Error("chart payload has an unsupported chartType");
  }
  return {
    id: "",
    type: "chart",
    schemaVersion: 1,
    title: "",
    chartType: chartType as ChartArtifact["chartType"],
    sourceResultArtifactId: requiredString(
      payload.sourceResultArtifactId,
      "sourceResultArtifactId",
    ),
    x: typeof payload.x === "string" ? payload.x : "",
    y: Array.isArray(payload.y)
      ? payload.y.filter((item): item is string => typeof item === "string")
      : [],
    aggregation:
      payload.aggregation === "sum" || payload.aggregation === "none"
        ? payload.aggregation
        : null,
  };
}

function parseSqlPayload(value: unknown): SqlArtifact {
  const payload = asRecord(value);
  return {
    id: "",
    type: "sql",
    schemaVersion: 1,
    title: "",
    sql: requiredString(payload.sql, "sql"),
    dialect: typeof payload.dialect === "string" ? payload.dialect : undefined,
    purpose: typeof payload.purpose === "string" ? payload.purpose : undefined,
    validationStatus:
      typeof payload.validationStatus === "string"
        ? payload.validationStatus
        : undefined,
    executionStatus:
      typeof payload.executionStatus === "string"
        ? payload.executionStatus
        : undefined,
    rowCount:
      typeof payload.rowCount === "number" ? payload.rowCount : undefined,
    latencyMs:
      typeof payload.latencyMs === "number" ? payload.latencyMs : undefined,
  };
}

export function createDataArtifactRenderers(
  actions: DataArtifactRendererActions = {},
): ReadonlyArray<ArtifactRendererContribution<unknown>> {
  return [
    {
      type: "result_view",
      supportedSchemaVersions: [1],
      parsePayload: parseResultViewPayload,
      render: (artifact, context) => {
        const parsed = parseResultViewPayload(artifact.payload);
        const model = { ...parsed, id: artifact.id, title: artifact.title };
        return (
          <TableArtifactView
            artifact={model}
            onToast={context.onToast}
            onOpenResultTab={actions.onOpenResultTab}
            sourceSqlArtifact={actions.sourceSqlArtifact}
            onOpenSqlConsole={actions.onOpenSqlConsole}
            mode={context.mode ?? "inline"}
          />
        );
      },
    },
    {
      type: "chart",
      supportedSchemaVersions: [1],
      parsePayload: parseChartPayload,
      render: (artifact, context) => {
        const model = {
          ...parseChartPayload(artifact.payload),
          id: artifact.id,
          title: artifact.title,
        };
        return (
          <DeferredChartArtifactView
            artifact={model}
            onToast={context.onToast}
            compact={context.compact}
          />
        );
      },
    },
    {
      type: "sql",
      supportedSchemaVersions: [1],
      parsePayload: parseSqlPayload,
      render: (artifact, context) => {
        if (!actions.onOpenSqlConsole) {
          throw new Error("SQL renderer requires a console action");
        }
        const model = {
          ...parseSqlPayload(artifact.payload),
          id: artifact.id,
          title: artifact.title,
        };
        return (
          <SqlArtifactView
            artifact={model}
            onOpenSqlConsole={actions.onOpenSqlConsole}
            onToast={context.onToast}
          />
        );
      },
    },
  ];
}

export const dataArtifactRenderers = createDataArtifactRenderers();
