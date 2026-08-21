import { randomBytes } from "node:crypto";
import { lstat, mkdir, open, readFile, readdir, rename, rm, stat } from "node:fs/promises";
import { basename, join } from "node:path";
import { strToU8, zipSync } from "fflate";

import type { DiagnosticBundlePayload, DiagnosticBundleResult, EngineStartupStatus } from "../shared/desktopContract";

const MAX_INPUT_BYTES = 1024 * 1024;
const MAX_STRING_CHARS = 64 * 1024;
const MAX_HOST_LOG_BYTES = 256 * 1024;
const MAX_DEPTH = 16;
const SENSITIVE_KEY = /(^|_)(password|passwd|pwd|secret|token|api_key|authorization|cookie|connection_string|dsn)$/i;
const ASSIGNMENT_RE = /(["']?\b(?:api[_-]?key|admin[_-]?api[_-]?key|openai[_-]?api[_-]?key|aliyun[_-]?api[_-]?key|password|passwd|pwd|secret|token|cookie|connection[_-]?string|dsn)\b["']?\s*[:=]\s*)(["']?)([^"'\s,;}\]]+)(["']?)/gi;
const AUTHORIZATION_RE = /\b(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)/gi;
const URL_PASSWORD_RE = /(\/\/[^:/@\s]+:)([^@/\s]+)(@)/g;

export async function exportDiagnosticBundle(
  logDirectory: string,
  payload: DiagnosticBundlePayload,
  appVersion: string,
  status: EngineStartupStatus,
): Promise<DiagnosticBundleResult> {
  const engine = sanitizeSnapshot(payload.engineSnapshot);
  const webview = sanitizeSnapshot(payload.webviewSnapshot);
  const createdAtUnix = Math.floor(Date.now() / 1000);
  const entries: Record<string, Uint8Array> = {
    "manifest.json": jsonBytes({
      schemaVersion: 1,
      createdAtUnix,
      host: {
        appVersion,
        os: process.platform,
        arch: process.arch,
        engineState: status.state,
        engineGeneration: status.generation,
        engineRestartCount: status.restartCount,
      },
      policy: {
        redacted: true,
        maxSnapshotBytes: MAX_INPUT_BYTES,
        maxHostLogBytes: MAX_HOST_LOG_BYTES,
        excluded: ["credentials", "local engine token", "database contents", "query result rows"],
      },
    }),
    "engine.json": jsonBytes(engine),
    "webview.json": jsonBytes(webview),
  };
  for (const baseName of ["dbfox-sidecar", "dbfox-host"]) {
    for (const path of await diagnosticLogFiles(logDirectory, baseName)) {
      const content = await readRegularLog(path);
      if (content !== null) entries[`host/${basename(path)}`] = strToU8(redactText(content));
    }
  }
  const archive = zipSync(entries, { level: 0 });
  const bundleDirectory = join(logDirectory, "diagnostic-bundles");
  await mkdir(bundleDirectory, { recursive: true, mode: 0o700 });
  const fileName = `dbfox-diagnostics-${createdAtUnix}-${randomBytes(8).toString("hex")}.zip`;
  const finalPath = join(bundleDirectory, fileName);
  const temporaryPath = `${finalPath}.tmp`;
  try {
    const handle = await open(temporaryPath, "wx", 0o600);
    try {
      await handle.writeFile(archive);
      await handle.sync();
    } finally {
      await handle.close();
    }
    await rename(temporaryPath, finalPath);
  } catch (error) {
    await rm(temporaryPath, { force: true });
    throw error;
  }
  return { path: finalPath, sizeBytes: (await stat(finalPath)).size, createdAtUnix };
}

export function sanitizeSnapshot(value: unknown): unknown {
  const sanitized = sanitizeValue(value, 0);
  if (Buffer.byteLength(JSON.stringify(sanitized)) > MAX_INPUT_BYTES) {
    throw new Error(`Diagnostic snapshot exceeds ${MAX_INPUT_BYTES} bytes`);
  }
  return sanitized;
}

export function redactText(text: string): string {
  return [...text].slice(0, MAX_STRING_CHARS).join("")
    .replace(URL_PASSWORD_RE, "$1[REDACTED]$3")
    .replace(AUTHORIZATION_RE, (_match, prefix: string, bearer: string | undefined) => `${prefix}${bearer ?? ""}[REDACTED]`)
    .replace(ASSIGNMENT_RE, (_match, prefix: string, quote: string, _value: string, closing: string) => `${prefix}${quote}[REDACTED]${closing}`);
}

function sanitizeValue(value: unknown, depth: number): unknown {
  if (depth >= MAX_DEPTH) return "[Maximum diagnostic depth reached]";
  if (typeof value === "string") return redactText(value);
  if (Array.isArray(value)) return value.slice(0, 2_000).map((item) => sanitizeValue(item, depth + 1));
  if (value !== null && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value).slice(0, 1_000)) {
      const normalized = key.toLowerCase().replaceAll("-", "_");
      output[key] = SENSITIVE_KEY.test(normalized) ? "[REDACTED]" : sanitizeValue(child, depth + 1);
    }
    return output;
  }
  return value;
}

async function diagnosticLogFiles(directory: string, baseName: string): Promise<string[]> {
  let names: string[];
  try {
    names = await readdir(directory);
  } catch {
    return [];
  }
  const active = `${baseName}.log`;
  return names.filter((name) => name === active || (name.startsWith(`${baseName}_`) && name.endsWith(".log")))
    .sort((left, right) => left === active ? -1 : right === active ? 1 : right.localeCompare(left))
    .slice(0, 4)
    .map((name) => join(directory, name));
}

async function readRegularLog(path: string): Promise<string | null> {
  const metadata = await lstat(path);
  if (!metadata.isFile()) return null;
  const bytes = await readFile(path);
  return bytes.subarray(Math.max(0, bytes.length - MAX_HOST_LOG_BYTES)).toString("utf8");
}

function jsonBytes(value: unknown): Uint8Array {
  return strToU8(`${JSON.stringify(value, null, 2)}\n`);
}
