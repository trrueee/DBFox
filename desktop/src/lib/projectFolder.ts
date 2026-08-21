import {
  listDesktopProjectFolder,
  pickDesktopProjectFolder,
  readDesktopProjectFile,
} from "./desktopHost";
import type { ProjectFileContent, ProjectFolderListing } from "./desktopHost";
export type { ProjectFileContent, ProjectFolderEntry, ProjectFolderListing } from "./desktopHost";

export async function pickProjectFolder(): Promise<string | null> {
  return pickDesktopProjectFolder();
}

export async function listProjectFolder(path: string): Promise<ProjectFolderListing> {
  return listDesktopProjectFolder(path);
}

export async function readProjectFile(path: string): Promise<ProjectFileContent> {
  return readDesktopProjectFile(path);
}
