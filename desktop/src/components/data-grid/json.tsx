import { useState } from "react";

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

export function JsonTree({ data, depth = 0 }: { data: JsonValue; depth?: number }) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  if (data === null) return <span className="text-[var(--text-muted)]">null</span>;
  if (typeof data === "boolean") return <span className="font-bold text-[var(--accent-indigo)]">{String(data)}</span>;
  if (typeof data === "number") return <span className="font-bold text-[var(--accent-green)]">{data}</span>;
  if (typeof data === "string") return <span className="text-[var(--accent-amber)]">&quot;{data}&quot;</span>;

  const isArray = Array.isArray(data);
  const keys = isArray ? data.map((_, index) => String(index)) : Object.keys(data);

  return (
    <div style={{ paddingLeft: depth > 0 ? 12 : 0 }}>
      <span className="text-[var(--text-muted)]">{isArray ? "[" : "{"}</span>
      <div className="ml-1.5 border-l border-dashed border-[var(--border-light)] pl-2">
        {keys.map((key) => {
          const value = isArray ? data[Number(key)] : data[key];
          const expandable = value !== null && typeof value === "object";
          const isCollapsed = collapsed[key];
          return (
            <div key={key} className="my-0.5">
              {!isArray && <span className="mr-1 font-semibold text-[var(--text-secondary)]">&quot;{key}&quot;:</span>}
              {expandable && (
                <button
                  type="button"
                  className="mr-1 border-0 bg-transparent px-1 font-mono text-[var(--ui-font-label)] text-[var(--text-muted)] cursor-pointer"
                  onClick={() => setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }))}
                >
                  {isCollapsed ? "▶" : "▼"}
                </button>
              )}
              {expandable && isCollapsed ? (
                <span className="text-[var(--ui-font-control)] text-[var(--text-muted)]">{compactJsonPreview(value)}</span>
              ) : expandable ? (
                <JsonTree data={value} depth={depth + 1} />
              ) : (
                <JsonTree data={value} depth={depth + 1} />
              )}
              {key !== keys[keys.length - 1] && <span className="text-[var(--text-muted)]">,</span>}
            </div>
          );
        })}
      </div>
      <span className="text-[var(--text-muted)]">{isArray ? "]" : "}"}</span>
    </div>
  );
}
