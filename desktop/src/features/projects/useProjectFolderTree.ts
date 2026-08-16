import { useCallback, useRef, useState } from "react";
import {
  listProjectFolder,
  type ProjectFolderEntry,
  type ProjectFolderListing,
} from "../../lib/projectFolder";

/**
 * Lazy project-folder tree state for the Workbench Shell sidebar.
 *
 * The Rust host exposes one folder level per call; directories are only read
 * after the user expands them, so large workspace roots stay bounded.
 */
export function useProjectFolderTree() {
  const [listings, setListings] = useState<Record<string, ProjectFolderListing | null>>({});
  const [loadingPaths, setLoadingPaths] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [expandedFolders, setExpandedFolders] = useState<string[]>([]);
  const loadedRef = useRef(new Set<string>());
  const pendingRef = useRef(new Set<string>());

  const loadFolder = useCallback(async (folderPath: string, force = false) => {
    const path = folderPath.trim();
    if (!path) return;
    if (loadedRef.current.has(path) && !force) return;
    if (pendingRef.current.has(path)) return;

    pendingRef.current.add(path);
    setLoadingPaths((current) => ({ ...current, [path]: true }));
    setErrors((current) => {
      if (!current[path]) return current;
      const next = { ...current };
      delete next[path];
      return next;
    });

    try {
      const listing = await listProjectFolder(path);
      if (listing.error) {
        throw new Error(listing.error);
      }
      loadedRef.current.add(path);
      setListings((current) => ({ ...current, [path]: listing }));
    } catch (error: unknown) {
      loadedRef.current.delete(path);
      setErrors((current) => ({
        ...current,
        [path]: error instanceof Error ? error.message : "读取文件夹失败，请重试。",
      }));
    } finally {
      pendingRef.current.delete(path);
      setLoadingPaths((current) => ({ ...current, [path]: false }));
    }
  }, []);

  const toggleFolder = useCallback(
    (entry: ProjectFolderEntry) => {
      if (expandedFolders.includes(entry.path)) {
        setExpandedFolders((current) => current.filter((item) => item !== entry.path));
        return;
      }
      setExpandedFolders((current) => [...current, entry.path]);
      void loadFolder(entry.path);
    },
    [expandedFolders, loadFolder],
  );

  return {
    listings,
    loadingPaths,
    errors,
    expandedFolders,
    loadFolder,
    toggleFolder,
  };
}
