import { parseExternalHttpsUrl } from "../../lib/externalNavigation";
import { isImageUrl } from "../imageUrl";
import { compactJsonPreview, tryParseJson, type JsonValue } from "./jsonValue";

export type CellValueKind =
  | "null"
  | "boolean"
  | "number"
  | "datetime"
  | "json"
  | "image-url"
  | "url"
  | "binary-placeholder"
  | "text";

export interface CellValuePresentation {
  kind: CellValueKind;
  rawText: string;
  displayText: string;
  copyText: string;
  parsedJson: JsonValue | null;
  previewable: boolean;
}

interface ClassifyCellValueOptions {
  dataType?: string;
}

const NUMERIC_TYPE_PATTERN = /\b(?:tiny|small|medium|big)?int(?:eger)?\b|\b(serial|numeric|decimal|float|double|real|money)\b/i;
const BOOLEAN_TYPE_PATTERN = /\b(bool|boolean)\b/i;
const TEMPORAL_TYPE_PATTERN = /\b(date|time|timestamp|datetime)\b/i;
const JSON_TYPE_PATTERN = /\b(json|jsonb)\b/i;
const BINARY_TYPE_PATTERN = /\b(blob|binary|varbinary|bytea|image)\b/i;

export function cellValueToText(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function getCellPreviewJson(value: unknown, displayValue = cellValueToText(value)): JsonValue | null {
  const parsedText = tryParseJson(displayValue);
  if (parsedText !== null) return parsedText;
  if (value === null || typeof value !== "object") return null;
  try {
    return JSON.parse(JSON.stringify(value)) as JsonValue;
  } catch {
    return null;
  }
}

export function isCellValuePreviewable(value: unknown, displayValue = cellValueToText(value)) {
  return getCellPreviewJson(value, displayValue) !== null || displayValue.length > 40 || displayValue.includes("\n");
}

export function classifyCellValue(
  value: unknown,
  { dataType = "" }: ClassifyCellValueOptions = {},
): CellValuePresentation {
  if (value === null || value === undefined) {
    return presentation("null", "", "NULL", "NULL", null, false);
  }

  const rawText = cellValueToText(value);
  if (typeof value === "boolean" || BOOLEAN_TYPE_PATTERN.test(dataType)) {
    const normalized = normalizeBoolean(value);
    return presentation("boolean", rawText, normalized ?? rawText, rawText, null, false);
  }

  if (typeof value === "number" || NUMERIC_TYPE_PATTERN.test(dataType)) {
    return presentation("number", rawText, rawText, rawText, null, false);
  }

  if (rawText === "<binary>" && BINARY_TYPE_PATTERN.test(dataType)) {
    return presentation("binary-placeholder", rawText, "BINARY · 未加载", rawText, null, true);
  }

  const parsedJson = getCellPreviewJson(value, rawText);
  if (parsedJson !== null || JSON_TYPE_PATTERN.test(dataType)) {
    return presentation(
      "json",
      rawText,
      parsedJson === null ? "JSON · 无法完整解析" : `JSON · ${compactJsonPreview(parsedJson)}`,
      rawText,
      parsedJson,
      true,
    );
  }

  if (typeof value === "string") {
    const externalUrl = parseExternalHttpsUrl(value);
    if (externalUrl && isImageUrl(externalUrl.href)) {
      return presentation("image-url", rawText, rawText, rawText, null, true);
    }
    if (externalUrl) {
      return presentation("url", rawText, rawText, rawText, null, true);
    }
  }

  const temporalDisplay = formatTemporalCellValue(value, dataType);
  if (temporalDisplay) {
    return presentation("datetime", rawText, temporalDisplay, rawText, null, false);
  }

  return presentation(
    "text",
    rawText,
    rawText,
    rawText,
    null,
    rawText.length > 40 || rawText.includes("\n"),
  );
}

export function isNumericCellType(dataType = "") {
  return NUMERIC_TYPE_PATTERN.test(dataType);
}

export function isTemporalCellType(dataType = "") {
  return TEMPORAL_TYPE_PATTERN.test(dataType);
}

function presentation(
  kind: CellValueKind,
  rawText: string,
  displayText: string,
  copyText: string,
  parsedJson: JsonValue | null,
  previewable: boolean,
): CellValuePresentation {
  return { kind, rawText, displayText, copyText, parsedJson, previewable };
}

function normalizeBoolean(value: unknown) {
  if (value === true || value === "true" || value === "TRUE" || value === 1 || value === "1") return "TRUE";
  if (value === false || value === "false" || value === "FALSE" || value === 0 || value === "0") return "FALSE";
  return null;
}

function formatTemporalCellValue(value: unknown, dataType: string) {
  const text = value instanceof Date
    ? value.toISOString()
    : typeof value === "string" || typeof value === "number"
      ? String(value)
      : "";
  if (!text || !TEMPORAL_TYPE_PATTERN.test(dataType)) return "";
  const match = text.trim().match(
    /^(\d{4}-\d{2}-\d{2})(?:[T\s](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:Z|[+-]\d{2}:?\d{2})?)?$/,
  );
  if (!match) return "";
  if (!match[2]) return match[1];
  const fraction = (match[3] ?? "").slice(0, 3).replace(/0+$/, "");
  return `${match[1]} ${match[2]}${fraction ? `.${fraction}` : ""}`;
}
