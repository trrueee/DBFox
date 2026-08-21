import { readFile, stat } from "node:fs/promises";
import { isAbsolute, join, relative } from "node:path";
import type { Protocol } from "electron";

const APP_SCHEME = "dbfox-app";
const MAX_APP_ASSET_BYTES = 10 * 1024 * 1024;
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "base-uri 'none'",
  "object-src 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
  "script-src 'self' dlc-asset:",
  "script-src-attr 'none'",
  "style-src 'self' dlc-asset: 'unsafe-inline'",
  "connect-src 'self' http://127.0.0.1:*",
  "img-src 'self' data: https: dlc-asset:",
  "font-src 'self' dlc-asset:",
].join("; ");

export const PACKAGED_RENDERER_URL = new URL(`${APP_SCHEME}://localhost/index.html`);

export function hasPackagedRendererOrigin(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl);
    return url.protocol === PACKAGED_RENDERER_URL.protocol
      && url.hostname.toLowerCase() === PACKAGED_RENDERER_URL.hostname
      && !url.username && !url.password && !url.port;
  } catch {
    return false;
  }
}

export function registerAppProtocol(protocol: Protocol, rendererRoot: string): void {
  protocol.handle(APP_SCHEME, (request) => handleAppRequest(request, rendererRoot));
}

export async function handleAppRequest(request: Request, rendererRoot: string): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") return response(405, "Method not allowed");
  let subpath: string;
  try {
    subpath = parseAppUrl(request.url);
  } catch {
    return response(400, "Invalid application URL");
  }
  const target = join(rendererRoot, subpath);
  const child = relative(rendererRoot, target);
  if (child === "" || child === ".." || child.startsWith("../") || child.startsWith("..\\") || isAbsolute(child)) {
    return response(403, "Application path traversal forbidden");
  }
  try {
    const metadata = await stat(target);
    if (!metadata.isFile()) return response(404, "Application asset not found");
    if (metadata.size > MAX_APP_ASSET_BYTES) return response(413, "Application asset exceeds size limit");
    const headers = securityHeaders(subpath === "index.html" ? "no-cache" : "public, max-age=31536000, immutable");
    headers.set("Content-Type", mimeForPath(target));
    if (request.method === "HEAD") return new Response(null, { status: 200, headers });
    return new Response(await readFile(target), { status: 200, headers });
  } catch (error) {
    if (isNodeError(error, "ENOENT")) return response(404, "Application asset not found");
    return response(500, "Application asset could not be read");
  }
}

export function parseAppUrl(rawUrl: string): string {
  const url = new URL(rawUrl);
  if (url.protocol !== `${APP_SCHEME}:` || url.hostname.toLowerCase() !== "localhost"
    || url.username || url.password || url.port || url.search || url.hash) {
    throw new Error("Invalid packaged renderer URL");
  }
  const segments = url.pathname.split("/").filter(Boolean).map((segment) => decodeURIComponent(segment));
  if (segments.length === 0) return "index.html";
  if (segments.some((segment) => segment === "." || segment === ".." || segment.includes("/")
    || segment.includes("\\") || segment.includes("\0"))) {
    throw new Error("Invalid packaged renderer path");
  }
  return segments.join("/");
}

function response(status: number, body: string): Response {
  const headers = securityHeaders("no-cache");
  headers.set("Content-Type", "text/plain; charset=utf-8");
  return new Response(body, { status, headers });
}

function securityHeaders(cacheControl: string): Headers {
  return new Headers({
    "Cache-Control": cacheControl,
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
  });
}

function mimeForPath(path: string): string {
  const extension = path.split(".").pop()?.toLowerCase();
  return ({
    html: "text/html; charset=utf-8", js: "text/javascript; charset=utf-8", mjs: "text/javascript; charset=utf-8",
    css: "text/css; charset=utf-8", json: "application/json; charset=utf-8", svg: "image/svg+xml",
    png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp", gif: "image/gif",
    ico: "image/x-icon", woff: "font/woff", woff2: "font/woff2", ttf: "font/ttf", otf: "font/otf",
  } as Record<string, string>)[extension ?? ""] ?? "application/octet-stream";
}

function isNodeError(error: unknown, code: string): boolean {
  return error instanceof Error && "code" in error && error.code === code;
}
