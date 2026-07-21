import { tryParseJson, type JsonValue } from "./jsonValue";

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
