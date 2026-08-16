import { invoke } from "@tauri-apps/api/core";

interface ProjectFolderSelection {
  path?: string | null;
}

export interface ProjectFolderEntry {
  name: string;
  path: string;
  isDir: boolean;
}

export interface ProjectFolderListing {
  path: string;
  entries: ProjectFolderEntry[];
  truncated: boolean;
  error?: string | null;
}

export interface ProjectFileContent {
  path: string;
  name: string;
  content?: string | null;
  binary: boolean;
  size: number;
  error?: string | null;
}

export async function pickProjectFolder(): Promise<string | null> {
  const result = await invoke<ProjectFolderSelection>("pick_project_folder");
  return result.path ?? null;
}

export async function listProjectFolder(path: string): Promise<ProjectFolderListing> {
  return invoke<ProjectFolderListing>("list_project_folder", { path });
}

export async function readProjectFile(path: string): Promise<ProjectFileContent> {
  return invoke<ProjectFileContent>("read_project_file", { path });
}
