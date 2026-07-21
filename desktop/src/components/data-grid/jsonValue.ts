export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export function tryParseJson(value: unknown): JsonValue | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!(trimmed.startsWith("{") && trimmed.endsWith("}")) && !(trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    return null;
  }
  try {
    return JSON.parse(trimmed) as JsonValue;
  } catch {
    return null;
  }
}

export function compactJsonPreview(value: JsonValue) {
  if (Array.isArray(value)) return `Array(${value.length})`;
  if (value && typeof value === "object") return `Object(${Object.keys(value).length})`;
  return String(value);
}
