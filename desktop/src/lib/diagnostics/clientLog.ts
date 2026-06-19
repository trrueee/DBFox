import type { DiagnosticLogSource } from "../api/diagnostics";

type ClientLogLevel = "info" | "warning" | "error";

interface ClientLogEntry {
  at: string;
  level: ClientLogLevel;
  message: string;
  detail?: string;
}

const STORAGE_KEY = "dbfox.clientLogs.v1";
const MAX_ENTRIES = 200;
const INSTALL_FLAG = "__DBFOX_CLIENT_LOG_INSTALLED__";

const ASSIGNMENT_RE =
  /(["']?\b(?:api[_-]?key|admin[_-]?api[_-]?key|openai[_-]?api[_-]?key|aliyun[_-]?api[_-]?key|password|passwd|pwd|secret|token|cookie|connection[_-]?string|dsn)\b["']?\s*[:=]\s*)(["']?)([^"'\s,;}\]]+)(["']?)/gi;
const AUTHORIZATION_RE = /\b(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)/gi;
const URL_PASSWORD_RE = /(\/\/[^:/@\s]+:)([^@/\s]+)(@)/g;

export function recordClientLog(level: ClientLogLevel, message: string, detail?: unknown): void {
  const entries = readEntries();
  entries.push({
    at: new Date().toISOString(),
    level,
    message: redactSensitiveText(message),
    detail: detail === undefined ? undefined : redactSensitiveText(safeStringify(detail)),
  });
  writeEntries(entries.slice(-MAX_ENTRIES));
}

export function getClientLogSource(): DiagnosticLogSource {
  const entries = readEntries();
  const content = entries
    .map((entry) => {
      const detail = entry.detail ? ` ${entry.detail}` : "";
      return `${entry.at} ${entry.level.toUpperCase()} ${entry.message}${detail}`;
    })
    .join("\n");

  return {
    name: "frontend-client",
    path: `localStorage:${STORAGE_KEY}`,
    exists: entries.length > 0,
    size_bytes: new Blob([content]).size,
    modified_at: entries.length > 0 ? entries[entries.length - 1].at : null,
    content,
  };
}

export function installClientErrorLogging(): void {
  if (typeof window === "undefined") return;
  const target = window as unknown as Window & Record<string, unknown>;
  if (target[INSTALL_FLAG]) return;
  target[INSTALL_FLAG] = true;

  window.addEventListener("error", (event) => {
    recordClientLog("error", event.message || "Unhandled frontend error", {
      source: event.filename,
      line: event.lineno,
      column: event.colno,
      stack: event.error instanceof Error ? event.error.stack : undefined,
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    recordClientLog("error", reason instanceof Error ? reason.message : "Unhandled promise rejection", {
      stack: reason instanceof Error ? reason.stack : undefined,
      reason: reason instanceof Error ? undefined : reason,
    });
  });
}

export function redactSensitiveText(text: string): string {
  return text
    .replace(URL_PASSWORD_RE, "$1[REDACTED]$3")
    .replace(AUTHORIZATION_RE, (_match, prefix: string, bearer: string | undefined) => `${prefix}${bearer ?? ""}[REDACTED]`)
    .replace(ASSIGNMENT_RE, (_match, prefix: string, quote: string, _value: string, closing: string) => `${prefix}${quote}[REDACTED]${closing}`);
}

function readEntries(): ClientLogEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isClientLogEntry) : [];
  } catch {
    return [];
  }
}

function writeEntries(entries: ClientLogEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // Diagnostics must never break the app.
  }
}

function isClientLogEntry(value: unknown): value is ClientLogEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as Partial<ClientLogEntry>;
  return (
    typeof entry.at === "string" &&
    (entry.level === "info" || entry.level === "warning" || entry.level === "error") &&
    typeof entry.message === "string"
  );
}

function safeStringify(value: unknown): string {
  if (value instanceof Error) {
    return JSON.stringify({ name: value.name, message: value.message, stack: value.stack });
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
