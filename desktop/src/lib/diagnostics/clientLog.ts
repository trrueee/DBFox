import type { DiagnosticLogSource } from "../api/diagnostics";
import { isTauri } from "@tauri-apps/api/core";
import { error as hostError, info as hostInfo, warn as hostWarn } from "@tauri-apps/plugin-log";

type ClientLogLevel = "info" | "warning" | "error";

interface ClientLogEntry {
  at: string;
  level: ClientLogLevel;
  message: string;
  detail?: string;
}

const STORAGE_KEY = "dbfox.clientLogs.v1";
const MAX_ENTRIES = 200;
const RETENTION_MS = 7 * 24 * 60 * 60 * 1_000;
const MAX_MESSAGE_CHARS = 2 * 1024;
const MAX_DETAIL_CHARS = 16 * 1024;
const INSTALL_FLAG = "__DBFOX_CLIENT_LOG_INSTALLED__";

const ASSIGNMENT_RE =
  /(["']?\b(?:api[_-]?key|admin[_-]?api[_-]?key|openai[_-]?api[_-]?key|aliyun[_-]?api[_-]?key|password|passwd|pwd|secret|token|cookie|connection[_-]?string|dsn)\b["']?\s*[:=]\s*)(["']?)([^"'\s,;}\]]+)(["']?)/gi;
const AUTHORIZATION_RE = /\b(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)/gi;
const URL_PASSWORD_RE = /(\/\/[^:/@\s]+:)([^@/\s]+)(@)/g;

export function recordClientLog(level: ClientLogLevel, message: string, detail?: unknown): void {
  const entries = readEntries();
  const entry: ClientLogEntry = {
    at: new Date().toISOString(),
    level,
    message: redactSensitiveText(message).slice(0, MAX_MESSAGE_CHARS),
    detail: detail === undefined
      ? undefined
      : redactSensitiveText(safeStringify(detail)).slice(0, MAX_DETAIL_CHARS),
  };
  entries.push(entry);
  writeEntries(entries.slice(-MAX_ENTRIES));
  emitDesktopLog(entry);
}

function emitDesktopLog(entry: ClientLogEntry): void {
  if (!isTauri()) return;
  const message = JSON.stringify({
    component: "webview",
    at: entry.at,
    message: entry.message,
    detail: entry.detail,
  });
  const operation = entry.level === "error"
    ? hostError(message)
    : entry.level === "warning"
      ? hostWarn(message)
      : hostInfo(message);
  void operation.catch(() => {
    // A logging transport failure must never affect product behavior.
  });
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
    if (!Array.isArray(parsed)) return [];
    const cutoff = Date.now() - RETENTION_MS;
    return parsed.filter(isClientLogEntry).filter((entry) => {
      const timestamp = Date.parse(entry.at);
      return Number.isFinite(timestamp) && timestamp >= cutoff;
    });
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
  const seen = new WeakSet<object>();
  try {
    const serialized = JSON.stringify(value, (_key, candidate: unknown) => {
      if (typeof candidate === "bigint") return `${candidate.toString()}n`;
      if (candidate && typeof candidate === "object") {
        if (seen.has(candidate)) return "[Circular]";
        seen.add(candidate);
      }
      if (candidate instanceof Error) {
        return {
          name: candidate.name,
          message: candidate.message,
          stack: candidate.stack,
          ...Object.fromEntries(Object.entries(candidate)),
        };
      }
      return candidate;
    });
    return serialized ?? String(value);
  } catch {
    try {
      return String(value);
    } catch {
      return "[Unserializable diagnostic value]";
    }
  }
}
