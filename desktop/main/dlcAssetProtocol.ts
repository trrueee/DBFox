import { readFile, realpath, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { isAbsolute, join, relative } from "node:path";
import type { Protocol } from "electron";

import type { EngineConfig } from "../shared/desktopContract";
import { readBoundedBody } from "./nodeEngineHost";

const MAX_DLC_ASSET_BYTES = 20 * 1024 * 1024;
const MAX_ACTIVATION_RESPONSE_BYTES = 64 * 1024;

export interface ActiveDlcProjectionItem {
  dlc_id: string;
  package_version: string;
  package_digest: string;
  frontend_entrypoint: string | null;
}

export interface RuntimeDlcActivationProjection {
  snapshot_id: string;
  active_dlcs: ActiveDlcProjectionItem[];
}

export class DlcAssetAuthority {
  #projection: RuntimeDlcActivationProjection | null = null;
  #epoch = 0;

  clear(): void {
    this.#epoch += 1;
    this.#projection = null;
  }

  isActive(packageDigest: string): boolean {
    const digest = normalizeDigest(packageDigest);
    return this.#projection?.active_dlcs.some((item) => item.frontend_entrypoint?.trim()
      && normalizeDigest(item.package_digest) === digest) ?? false;
  }

  updateProjection(projection: RuntimeDlcActivationProjection): void {
    this.#epoch += 1;
    this.#projection = null;
    this.#projection = parseProjection(projection);
  }

  async synchronize(
    config: EngineConfig,
    rendererOrigin: string,
  ): Promise<RuntimeDlcActivationProjection> {
    const epoch = ++this.#epoch;
    this.#projection = null;
    const response = await fetch(`http://127.0.0.1:${config.port}/api/v1/dlcs/activation`, {
      headers: { Origin: rendererOrigin, "X-Local-Token": config.token },
      signal: AbortSignal.timeout(3_000),
    });
    const bytes = await readBoundedBody(response, MAX_ACTIVATION_RESPONSE_BYTES);
    if (!response.ok) throw new Error(`DLC activation projection returned HTTP ${response.status}`);
    const projection = parseProjection(JSON.parse(new TextDecoder().decode(bytes)));
    if (epoch === this.#epoch) this.#projection = projection;
    return projection;
  }
}

export function registerDlcAssetProtocol(protocol: Protocol, authority: DlcAssetAuthority): void {
  protocol.handle("dlc-asset", (request) => handleDlcAssetRequest(authority, request));
}

export async function handleDlcAssetRequest(
  authority: DlcAssetAuthority,
  request: Request,
  packagesRoot = resolveDlcPackagesRoot(),
): Promise<Response> {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders("no-cache") });
  }
  if (request.method !== "GET" && request.method !== "HEAD") return textResponse(405, "Method not allowed");
  let parsed: { packageDigest: string; subpath: string };
  try {
    parsed = parseDlcAssetUrl(request.url);
  } catch {
    return textResponse(400, "Invalid DLC asset URL");
  }
  if (!authority.isActive(parsed.packageDigest)) {
    return textResponse(403, "DLC package is not active in the current runtime snapshot");
  }
  if (packagesRoot === null) return textResponse(404, "DLC runtime directory is unavailable");
  try {
    const base = await realpath(join(packagesRoot, `sha256-${parsed.packageDigest}`, "frontend"));
    const target = await realpath(join(base, parsed.subpath));
    const child = relative(base, target);
    if (child === "" || child === ".." || child.startsWith("../") || child.startsWith("..\\") || isAbsolute(child)) {
      return textResponse(403, "Path traversal forbidden");
    }
    const metadata = await stat(target);
    if (!metadata.isFile()) return textResponse(404, "Requested path is not a file");
    if (metadata.size > MAX_DLC_ASSET_BYTES) return textResponse(413, "Asset file exceeds 20 MiB maximum size");
    const headers = corsHeaders("public, max-age=31536000, immutable");
    headers.set("Content-Type", mimeForPath(target));
    if (request.method === "HEAD") return new Response(null, { status: 200, headers });
    const bytes = await readFile(target);
    return new Response(bytes, { status: 200, headers });
  } catch (error) {
    if (isNodeError(error, "ENOENT")) return textResponse(404, "Asset file not found");
    return textResponse(500, "Failed to read asset file");
  }
}

export function parseDlcAssetUrl(rawUrl: string): { packageDigest: string; subpath: string } {
  const url = new URL(rawUrl);
  if (url.protocol !== "dlc-asset:") throw new Error("Invalid scheme");
  if (url.hostname && url.hostname !== "127.0.0.1" && url.hostname.toLowerCase() !== "localhost") {
    throw new Error("Invalid host");
  }
  const segments = url.pathname.split("/").filter(Boolean).map((segment) => decodeURIComponent(segment));
  const packageDigest = normalizeDigest(segments.shift() ?? "");
  if (!/^[0-9a-f]{64}$/.test(packageDigest)) throw new Error("Invalid package digest");
  if (segments[0] === "frontend") segments.shift();
  if (segments.length === 0 || segments.some((segment) => segment === "." || segment === ".."
    || segment.includes("/") || segment.includes("\\") || segment.includes("\0"))) {
    throw new Error("Invalid asset subpath");
  }
  return { packageDigest, subpath: segments.join("/") };
}

export function resolveDlcPackagesRoot(env = process.env): string | null {
  if (env.DBFOX_RUNTIME_DIR?.trim()) return join(env.DBFOX_RUNTIME_DIR, "dlcs", "packages");
  if (process.platform === "win32" && env.APPDATA?.trim()) return join(env.APPDATA, "DBFox", "dlcs", "packages");
  if (process.platform === "darwin") return join(homedir(), "Library", "Application Support", "DBFox", "dlcs", "packages");
  if (process.platform !== "win32") {
    const root = env.XDG_DATA_HOME?.trim() ? join(env.XDG_DATA_HOME, "dbfox") : join(homedir(), ".local", "share", "dbfox");
    return join(root, "dlcs", "packages");
  }
  return null;
}

function parseProjection(value: unknown): RuntimeDlcActivationProjection {
  if (value === null || typeof value !== "object") throw new Error("Invalid DLC activation projection");
  const record = value as Record<string, unknown>;
  if (!hasOnlyKeys(record, ["snapshot_id", "active_dlcs"])
    || typeof record.snapshot_id !== "string" || record.snapshot_id.length === 0 || record.snapshot_id.length > 256
    || !Array.isArray(record.active_dlcs) || record.active_dlcs.length > 256) {
    throw new Error("Invalid DLC activation projection");
  }
  const active_dlcs = record.active_dlcs.map((item) => {
    if (item === null || typeof item !== "object") throw new Error("Invalid active DLC item");
    const entry = item as Record<string, unknown>;
    if (!hasOnlyKeys(entry, ["dlc_id", "package_version", "package_digest", "frontend_entrypoint"])
      || typeof entry.dlc_id !== "string" || entry.dlc_id.length === 0 || entry.dlc_id.length > 256
      || typeof entry.package_version !== "string" || entry.package_version.length === 0 || entry.package_version.length > 128
      || typeof entry.package_digest !== "string"
      || !/^[0-9a-f]{64}$/.test(normalizeDigest(entry.package_digest))
      || !(entry.frontend_entrypoint === null || (typeof entry.frontend_entrypoint === "string"
        && entry.frontend_entrypoint.length <= 2_048))) {
      throw new Error("Invalid active DLC item");
    }
    return {
      dlc_id: entry.dlc_id,
      package_version: entry.package_version,
      package_digest: entry.package_digest,
      frontend_entrypoint: entry.frontend_entrypoint,
    };
  });
  return { snapshot_id: record.snapshot_id, active_dlcs };
}

function hasOnlyKeys(record: Record<string, unknown>, allowed: readonly string[]): boolean {
  return Object.keys(record).every((key) => allowed.includes(key));
}

function normalizeDigest(value: string): string {
  return value.replace(/^sha256[:-]/i, "").toLowerCase();
}

function corsHeaders(cacheControl: string): Headers {
  return new Headers({
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Cache-Control": cacheControl,
    "X-Content-Type-Options": "nosniff",
  });
}

function textResponse(status: number, body: string): Response {
  const headers = corsHeaders("no-cache");
  headers.set("Content-Type", "text/plain; charset=utf-8");
  return new Response(body, { status, headers });
}

function mimeForPath(path: string): string {
  const extension = path.split(".").pop()?.toLowerCase();
  return ({
    js: "text/javascript; charset=utf-8", mjs: "text/javascript; charset=utf-8", css: "text/css; charset=utf-8",
    json: "application/json; charset=utf-8", svg: "image/svg+xml", png: "image/png", jpg: "image/jpeg",
    jpeg: "image/jpeg", webp: "image/webp", gif: "image/gif", ico: "image/x-icon", woff: "font/woff",
    woff2: "font/woff2", ttf: "font/ttf", otf: "font/otf", html: "text/html; charset=utf-8",
  } as Record<string, string>)[extension ?? ""] ?? "application/octet-stream";
}

function isNodeError(error: unknown, code: string): boolean {
  return error instanceof Error && "code" in error && error.code === code;
}
