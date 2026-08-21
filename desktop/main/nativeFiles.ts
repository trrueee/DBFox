import { randomBytes } from "node:crypto";
import { mkdir, readFile, readdir, realpath, rename, rm, stat, writeFile } from "node:fs/promises";
import { basename, dirname, extname, isAbsolute, join, relative } from "node:path";

import type { ProjectFileContent, ProjectFolderListing } from "../shared/desktopContract";

const MAX_PROJECT_FOLDER_ENTRIES = 600;
const MAX_PROJECT_FILE_BYTES = 1024 * 1024;
const MAX_APPROVED_ROOTS = 64;
const SKIPPED_DIRECTORIES = new Set([
  ".git", "node_modules", ".venv", "venv", "__pycache__", "target", "dist", "build",
  ".next", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".turbo",
]);

export class ProjectFolderAccess {
  readonly #accessFile: string;

  constructor(accessFile: string) {
    this.#accessFile = accessFile;
  }

  async approve(path: string): Promise<string> {
    const canonical = await realpath(path);
    if (!(await stat(canonical)).isDirectory()) throw new Error("选择的项目路径不是文件夹");
    const roots = await this.#load();
    roots.add(canonical);
    if (roots.size > MAX_APPROVED_ROOTS) throw new Error("项目文件夹授权数量超过上限");
    await writeJsonAtomically(this.#accessFile, { schemaVersion: 1, roots: [...roots].sort() });
    return canonical;
  }

  async list(path: string): Promise<ProjectFolderListing> {
    try {
      const canonical = await this.#requireApproved(path);
      const items = await readdir(canonical, { withFileTypes: true });
      const entries = [];
      for (const item of items) {
        const child = join(canonical, item.name);
        let isDir = item.isDirectory();
        if (item.isSymbolicLink()) {
          try {
            isDir = (await stat(child)).isDirectory();
          } catch {
            continue;
          }
        }
        if (isDir && SKIPPED_DIRECTORIES.has(item.name)) continue;
        entries.push({ name: item.name, path: child, isDir });
      }
      entries.sort((left, right) => Number(right.isDir) - Number(left.isDir)
        || left.name.localeCompare(right.name, undefined, { sensitivity: "base" }));
      return {
        path: canonical,
        entries: entries.slice(0, MAX_PROJECT_FOLDER_ENTRIES),
        truncated: entries.length > MAX_PROJECT_FOLDER_ENTRIES,
        error: null,
      };
    } catch (error) {
      return { path, entries: [], truncated: false, error: errorMessage(error, "读取文件夹失败") };
    }
  }

  async read(path: string): Promise<ProjectFileContent> {
    const empty = { path, name: basename(path), content: null, binary: false, size: 0 };
    try {
      const canonical = await this.#requireApproved(path);
      const metadata = await stat(canonical);
      if (!metadata.isFile()) return { ...empty, error: "该路径不是文件" };
      if (metadata.size > MAX_PROJECT_FILE_BYTES) {
        return { ...empty, size: metadata.size, error: "文件超过 1 MiB，暂不在工作台内预览" };
      }
      const bytes = await readFile(canonical);
      if (bytes.subarray(0, 8192).includes(0)) {
        return { ...empty, path: canonical, size: metadata.size, binary: true, error: "二进制文件不支持预览" };
      }
      const decoder = new TextDecoder("utf-8", { fatal: true });
      try {
        return { ...empty, path: canonical, name: basename(canonical), content: decoder.decode(bytes), size: metadata.size, error: null };
      } catch {
        return { ...empty, path: canonical, size: metadata.size, binary: true, error: "文件编码不是 UTF-8，不支持预览" };
      }
    } catch (error) {
      return { ...empty, error: errorMessage(error, "读取文件失败") };
    }
  }

  async #requireApproved(path: string): Promise<string> {
    if (typeof path !== "string" || !isAbsolute(path)) throw new Error("项目路径必须是绝对路径");
    const canonical = await realpath(path);
    const roots = await this.#load();
    for (const root of roots) {
      const child = relative(root, canonical);
      if (child === "" || (!child.startsWith(`..${process.platform === "win32" ? "\\" : "/"}`)
        && child !== ".." && !isAbsolute(child))) return canonical;
    }
    throw new Error("该路径不在你选择过的项目文件夹内。");
  }

  async #load(): Promise<Set<string>> {
    let raw: string;
    try {
      raw = await readFile(this.#accessFile, "utf8");
    } catch (error) {
      if (isNodeError(error, "ENOENT")) return new Set();
      throw new Error("读取文件夹授权记录失败", { cause: error });
    }
    if (Buffer.byteLength(raw) > 64 * 1024) throw new Error("文件夹授权记录损坏");
    let value: unknown;
    try {
      value = JSON.parse(raw);
    } catch {
      throw new Error("文件夹授权记录损坏");
    }
    if (!isApprovedRoots(value)) throw new Error("文件夹授权记录损坏");
    return new Set(value.roots);
  }
}

export async function validateDlcPackage(path: string): Promise<string> {
  const canonical = await realpath(path);
  if (!(await stat(canonical)).isFile() || extname(canonical).toLowerCase() !== ".dbfox-dlc") {
    throw new Error("只能选择现有的 .dbfox-dlc 单文件安装包");
  }
  return canonical;
}

async function writeJsonAtomically(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = join(dirname(path), `.${basename(path)}.${randomBytes(8).toString("hex")}.tmp`);
  try {
    await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
    await rename(temporary, path);
  } catch (error) {
    await rm(temporary, { force: true });
    throw error;
  }
}

function isApprovedRoots(value: unknown): value is { schemaVersion: 1; roots: string[] } {
  if (value === null || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return Object.keys(record).every((key) => key === "schemaVersion" || key === "roots")
    && record.schemaVersion === 1
    && Array.isArray(record.roots)
    && record.roots.length <= MAX_APPROVED_ROOTS
    && record.roots.every((root) => typeof root === "string" && isAbsolute(root));
}

function isNodeError(error: unknown, code: string): boolean {
  return error instanceof Error && "code" in error && error.code === code;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? `${fallback}：${error.message}` : fallback;
}
