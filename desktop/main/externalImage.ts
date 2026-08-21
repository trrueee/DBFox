import { randomBytes } from "node:crypto";
import { lookup } from "node:dns/promises";
import { open, rename, rm } from "node:fs/promises";
import { request } from "node:https";
import { basename, dirname, extname, join } from "node:path";
import { isIP } from "node:net";

const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const MAX_REDIRECTS = 3;
const MAX_CONCURRENT_DOWNLOADS = 2;
const ALLOWED_MEDIA = new Map([
  ["image/png", "png"], ["image/jpeg", "jpg"], ["image/gif", "gif"], ["image/webp", "webp"],
  ["image/avif", "avif"], ["image/bmp", "bmp"], ["image/x-icon", "ico"], ["image/vnd.microsoft.icon", "ico"],
]);

export interface DownloadedImage {
  bytes: Uint8Array;
  extension: string;
  suggestedName: string;
}

let activeDownloads = 0;

export async function downloadExternalImage(rawUrl: string): Promise<DownloadedImage> {
  if (activeDownloads >= MAX_CONCURRENT_DOWNLOADS) throw new Error("图片下载服务繁忙，请稍后重试");
  activeDownloads += 1;
  try {
    return await downloadExternalImageWithinSlot(rawUrl);
  } finally {
    activeDownloads -= 1;
  }
}

async function downloadExternalImageWithinSlot(rawUrl: string): Promise<DownloadedImage> {
  let current = validateExternalImageUrl(rawUrl);
  for (let redirects = 0; redirects <= MAX_REDIRECTS; redirects += 1) {
    const response = await requestPinned(current);
    if (response.status >= 300 && response.status < 400) {
      if (redirects === MAX_REDIRECTS || !response.location) throw new Error("图片地址重定向次数过多或无效");
      current = validateExternalImageUrl(new URL(response.location, current).href);
      continue;
    }
    if (response.status !== 200) throw new Error("图片服务器未返回可下载内容");
    const mediaType = response.contentType.split(";", 1)[0]?.trim().toLowerCase() ?? "";
    const extension = ALLOWED_MEDIA.get(mediaType);
    if (!extension) throw new Error("仅支持保存 PNG、JPEG、GIF、WebP、AVIF、BMP 或 ICO 图片");
    if (!matchesImageSignature(response.bytes, extension)) throw new Error("下载内容与图片格式不匹配");
    return { bytes: response.bytes, extension, suggestedName: suggestedFileName(current, extension) };
  }
  throw new Error("图片地址重定向次数过多");
}

export function validateExternalImageUrl(rawUrl: string): URL {
  if (!rawUrl || rawUrl.trim() !== rawUrl) throw new Error("图片地址不能为空或包含首尾空格");
  const url = new URL(rawUrl);
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password || (url.port && url.port !== "443")) {
    throw new Error("仅允许下载使用标准端口且不含凭据的 HTTPS 图片");
  }
  if (url.hostname.toLowerCase() === "localhost" || url.hostname.toLowerCase().endsWith(".localhost")) {
    throw new Error("图片地址不能指向本机");
  }
  return url;
}

export async function persistImageAtomically(destination: string, image: DownloadedImage): Promise<string> {
  const finalPath = extname(destination).toLowerCase() === `.${image.extension}`
    ? destination
    : `${destination.slice(0, destination.length - extname(destination).length)}.${image.extension}`;
  const temporary = join(dirname(finalPath), `.${basename(finalPath)}.${randomBytes(8).toString("hex")}.tmp`);
  try {
    const handle = await open(temporary, "wx", 0o600);
    try {
      await handle.writeFile(image.bytes);
      await handle.sync();
    } finally {
      await handle.close();
    }
    await rename(temporary, finalPath);
    return finalPath;
  } catch (error) {
    await rm(temporary, { force: true });
    throw error;
  }
}

async function requestPinned(url: URL): Promise<{
  status: number; location: string | null; contentType: string; bytes: Uint8Array;
}> {
  const addresses = await lookup(url.hostname, { all: true, verbatim: true });
  const allowed = addresses.filter((address) => isPublicIp(address.address));
  if (allowed.length === 0 || allowed.length !== addresses.length) {
    throw new Error("图片地址指向本机、保留地址或私有网络，已拒绝下载");
  }
  const pinned = allowed[0];
  return new Promise((resolveResponse, reject) => {
    const operation = request(url, {
      method: "GET",
      headers: {
        Accept: "image/avif,image/webp,image/png,image/jpeg,image/gif,image/bmp,image/x-icon",
        "User-Agent": "DBFox/1 image-save",
      },
      lookup: (_hostname, _options, callback) => callback(null, pinned.address, pinned.family),
      timeout: 20_000,
    }, (response) => {
      const status = response.statusCode ?? 0;
      const contentLength = Number(response.headers["content-length"] ?? 0);
      if (Number.isFinite(contentLength) && contentLength > MAX_IMAGE_BYTES) {
        response.destroy(new Error("图片超过 20 MB 保存上限"));
        return;
      }
      const chunks: Buffer[] = [];
      let total = 0;
      response.on("data", (chunk: Buffer) => {
        total += chunk.byteLength;
        if (total > MAX_IMAGE_BYTES) response.destroy(new Error("图片超过 20 MB 保存上限"));
        else chunks.push(chunk);
      });
      response.once("end", () => resolveResponse({
        status,
        location: typeof response.headers.location === "string" ? response.headers.location : null,
        contentType: typeof response.headers["content-type"] === "string" ? response.headers["content-type"] : "",
        bytes: Buffer.concat(chunks, total),
      }));
      response.once("error", reject);
    });
    operation.once("timeout", () => operation.destroy(new Error("图片下载超时")));
    operation.once("error", reject);
  });
}

export function isPublicIp(value: string): boolean {
  const family = isIP(value);
  if (family === 4) {
    const [a, b, c] = value.split(".").map(Number);
    return !(a === 0 || a === 10 || a === 127 || (a === 100 && b >= 64 && b <= 127)
      || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31)
      || (a === 192 && b === 0 && (c === 0 || c === 2)) || (a === 192 && b === 168)
      || (a === 198 && (b === 18 || b === 19)) || (a === 198 && b === 51 && c === 100)
      || (a === 203 && b === 0 && c === 113) || a >= 224);
  }
  if (family === 6) {
    const normalized = value.toLowerCase();
    if (normalized.startsWith("::ffff:")) return isPublicIp(normalized.slice(7));
    return !(normalized === "::" || normalized === "::1" || normalized.startsWith("fc")
      || normalized.startsWith("fd") || /^fe[89ab]/.test(normalized) || normalized.startsWith("ff")
      || normalized.startsWith("2001:db8:"));
  }
  return false;
}

export function matchesImageSignature(bytes: Uint8Array, extension: string): boolean {
  const prefix = (...values: number[]) => values.every((value, index) => bytes[index] === value);
  if (extension === "png") return prefix(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a);
  if (extension === "jpg") return prefix(0xff, 0xd8, 0xff);
  if (extension === "gif") return new TextDecoder().decode(bytes.subarray(0, 6)) === "GIF87a"
    || new TextDecoder().decode(bytes.subarray(0, 6)) === "GIF89a";
  if (extension === "webp") return new TextDecoder().decode(bytes.subarray(0, 4)) === "RIFF"
    && new TextDecoder().decode(bytes.subarray(8, 12)) === "WEBP";
  if (extension === "bmp") return prefix(0x42, 0x4d);
  if (extension === "ico") return prefix(0, 0, 1, 0);
  if (extension === "avif") return new TextDecoder().decode(bytes.subarray(4, 8)) === "ftyp"
    && ["avif", "avis"].includes(new TextDecoder().decode(bytes.subarray(8, 12)));
  return false;
}

function suggestedFileName(url: URL, extension: string): string {
  const raw = decodeURIComponent(url.pathname.split("/").pop() || "dbfox-image");
  const stem = basename(raw, extname(raw)).split("").filter((character) => /[A-Za-z0-9._-]/.test(character)).join("").slice(0, 80);
  return `${stem || "dbfox-image"}.${extension}`;
}
