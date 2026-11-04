import { Archive, AudioLines, ChartNoAxesCombined, Database, File, FileCode2, FileImage, FileSpreadsheet, FileText, Film, Folder, FolderOpen, Package, Table2, type LucideIcon } from "lucide-react";
import type { WorkbenchReference } from "../../types/workspace";
import "./resources.css";

export type ResourceKind = import("../../features/dlc/types").HostResourceKind;

const PRESENTATION: Record<ResourceKind, { icon: LucideIcon; label: string }> = {
  file: { icon: File, label: "文件" }, folder: { icon: Folder, label: "文件夹" },
  code: { icon: FileCode2, label: "代码" }, markdown: { icon: FileText, label: "Markdown" },
  spreadsheet: { icon: FileSpreadsheet, label: "电子表格" }, database: { icon: Database, label: "数据库" },
  table: { icon: Table2, label: "数据表" }, chart: { icon: ChartNoAxesCombined, label: "图表" },
  image: { icon: FileImage, label: "图片" }, audio: { icon: AudioLines, label: "音频" },
  video: { icon: Film, label: "视频" }, document: { icon: FileText, label: "文档" },
  archive: { icon: Archive, label: "压缩文件" }, artifact: { icon: Package, label: "成果" },
  resource: { icon: File, label: "引用" },
};

// Unmodified official Fluent file artwork, canonical Markdown and code-language
// marks. Attribution and pinned hashes ship in public/licenses; all assets are local.
const FILE_TYPES: readonly { extensions: readonly string[]; kind: ResourceKind; icon?: string; sized?: boolean }[] = [
  { extensions: ["md", "markdown", "mdx"], kind: "markdown", icon: "markdown" },
  { extensions: ["xlsx", "xls", "xlsm", "xlsb"], kind: "spreadsheet", icon: "excel", sized: true },
  { extensions: ["csv", "tsv"], kind: "spreadsheet" },
  { extensions: ["ods"], kind: "spreadsheet" },
  { extensions: ["pdf"], kind: "document", icon: "pdf", sized: true },
  { extensions: ["doc", "docx"], kind: "document", icon: "word", sized: true },
  { extensions: ["ppt", "pptx"], kind: "document", icon: "powerpoint", sized: true },
  { extensions: ["rtf", "odt", "odp"], kind: "document" },
  { extensions: ["py", "pyw", "pyi"], kind: "code", icon: "python" },
  { extensions: ["ts", "mts", "cts"], kind: "code", icon: "typescript" },
  { extensions: ["js", "mjs", "cjs"], kind: "code", icon: "js_official" },
  { extensions: ["jsx"], kind: "code", icon: "reactjs" },
  { extensions: ["tsx"], kind: "code", icon: "reactts" },
  { extensions: ["json", "jsonc", "json5"], kind: "code", icon: "json" },
  { extensions: ["sql"], kind: "code", icon: "sql" },
  { extensions: ["html", "htm"], kind: "code", icon: "html" },
  { extensions: ["css"], kind: "code", icon: "css" },
  { extensions: ["yaml", "yml"], kind: "code", icon: "yaml" },
  { extensions: ["toml"], kind: "code", icon: "toml" },
  { extensions: ["rs"], kind: "code", icon: "rust" },
  { extensions: ["go"], kind: "code", icon: "go" },
  { extensions: ["java"], kind: "code", icon: "java" },
  { extensions: ["c", "h"], kind: "code", icon: "c" },
  { extensions: ["cpp", "cc", "cxx", "hpp"], kind: "code", icon: "cpp" },
  { extensions: ["cs"], kind: "code", icon: "csharp" },
  { extensions: ["ps1", "psm1", "psd1"], kind: "code", icon: "powershell" },
  { extensions: ["sh", "bash", "zsh"], kind: "code", icon: "shell" },
  { extensions: ["xml", "vue", "svelte", "swift", "kt", "kts", "rb", "php", "r", "lua", "scss", "sass", "less"], kind: "code" },
  { extensions: ["png", "jpg", "jpeg", "gif", "webp", "svg", "avif", "ico", "bmp", "tif", "tiff"], kind: "image", icon: "image", sized: true },
  { extensions: ["mp3", "wav", "ogg", "flac", "m4a", "mid", "midi", "aac", "aiff"], kind: "audio", icon: "audio", sized: true },
  { extensions: ["mp4", "webm", "mov", "mkv", "avi"], kind: "video", icon: "video", sized: true },
  { extensions: ["zip", "gz", "tar", "7z", "rar", "bz2", "xz"], kind: "archive", icon: "archive", sized: true },
  { extensions: ["txt", "log"], kind: "file", icon: "text", sized: true },
];

function filePresentation(name: string): { kind: ResourceKind; icon?: string; sized?: boolean } {
  const basename = name.split(/[\\/]/).at(-1)?.toLowerCase() ?? "";
  if (basename === "dockerfile" || basename.startsWith("dockerfile.")) return { kind: "code", icon: "docker" };
  if ([".gitignore", ".gitattributes", ".gitmodules"].includes(basename)) return { kind: "code", icon: "git" };
  const dot = basename.lastIndexOf(".");
  const extension = dot > 0 ? basename.slice(dot + 1) : "";
  return FILE_TYPES.find(type => type.extensions.includes(extension)) ?? { kind: "file" };
}

export function fileKind(name: string): ResourceKind { return filePresentation(name).kind; }

export function referenceKind(reference: WorkbenchReference): ResourceKind {
  if (reference.object?.kind === "dbfox.core.attachment") return fileKind(reference.label);
  if (reference.artifactId) return "artifact";
  const subject = reference.object?.kind.split(".").at(-1);
  if (subject === "file") return fileKind(reference.locator ?? reference.label);
  if (subject && Object.hasOwn(PRESENTATION, subject)) return subject as ResourceKind;
  return "resource";
}

export function resourceLabel(kind: ResourceKind): string { return PRESENTATION[kind].label; }

export function artifactKind(type: string): ResourceKind {
  const name = type.split(".").at(-1) ?? "";
  if (["dataframe", "result_view", "snapshot"].includes(name)) return "table";
  if (["chart", "visualization"].includes(name)) return "chart";
  if (["sql", "code_patch"].includes(name)) return "code";
  if (name === "markdown") return "markdown";
  if (["note", "chapter_revision"].includes(name)) return "document";
  if (["score_revision", "transcription"].includes(name)) return "audio";
  return "artifact";
}

export function ResourceIcon({ name = "", kind = fileKind(name), size = 16, className = "", expanded = false }: {
  name?: string; kind?: ResourceKind; size?: number; className?: string; expanded?: boolean;
}) {
  const file = filePresentation(name);
  const presentation = file.kind === kind ? file : kind === "markdown" ? { icon: "markdown", sized: false } : undefined;
  const asset = presentation?.icon;
  const suffix = presentation?.sized && size >= 20 ? "_20" : "";
  const source = asset ? `${import.meta.env.BASE_URL}assets/file-icons/file_type_${asset}${suffix}.svg` : undefined;
  const classes = `resource-icon resource-icon--${kind} ${className}`;
  if (source) return <img src={source} alt="" aria-hidden="true" width={size} height={size} draggable={false} className={classes} />;
  const Icon = kind === "folder" && expanded ? FolderOpen : PRESENTATION[kind]?.icon ?? File;
  return <Icon size={size} strokeWidth={1.75} aria-hidden="true" className={classes} />;
}
