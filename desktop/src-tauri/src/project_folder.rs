use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Manager};
use tauri_plugin_dialog::DialogExt;

const MAX_PROJECT_FOLDER_ENTRIES: usize = 600;
const MAX_PROJECT_FILE_BYTES: u64 = 1024 * 1024;
const PROJECT_FOLDER_ACCESS_FILE: &str = "project_folder_access.json";

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ProjectFolderSelection {
    path: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ProjectFolderEntry {
    name: String,
    path: String,
    is_dir: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ProjectFolderListing {
    path: String,
    entries: Vec<ProjectFolderEntry>,
    truncated: bool,
    error: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ProjectFileContent {
    path: String,
    name: String,
    content: Option<String>,
    binary: bool,
    size: u64,
    error: Option<String>,
}

#[derive(Debug, Default, Deserialize, Serialize)]
struct ApprovedProjectRoots {
    roots: Vec<String>,
}

fn access_file_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_config_dir()
        .map(|dir| dir.join(PROJECT_FOLDER_ACCESS_FILE))
        .map_err(|error| format!("无法定位应用配置目录：{error}"))
}

fn load_approved_roots(app: &AppHandle) -> Result<HashSet<PathBuf>, String> {
    let file = access_file_path(app)?;
    if !file.exists() {
        return Ok(HashSet::new());
    }
    let raw =
        fs::read_to_string(&file).map_err(|error| format!("读取文件夹授权记录失败：{error}"))?;
    let approved: ApprovedProjectRoots =
        serde_json::from_str(&raw).map_err(|error| format!("文件夹授权记录损坏：{error}"))?;
    Ok(approved.roots.into_iter().map(PathBuf::from).collect())
}

fn approve_root(app: &AppHandle, root: &Path) {
    let Ok(file) = access_file_path(app) else {
        return;
    };
    let mut roots = load_approved_roots(app).unwrap_or_default();
    roots.insert(root.to_path_buf());
    let approved = ApprovedProjectRoots {
        roots: roots.iter().map(|path| path_string(path)).collect(),
    };
    if let Some(parent) = file.parent() {
        if !parent.exists() {
            let _ = fs::create_dir_all(parent);
        }
    }
    if let Ok(raw) = serde_json::to_vec_pretty(&approved) {
        let _ = fs::write(file, raw);
    }
}

fn path_is_within_roots(path: &Path, approved: &HashSet<PathBuf>) -> bool {
    let Ok(canonical_path) = fs::canonicalize(path) else {
        return false;
    };
    approved.iter().any(|root| {
        fs::canonicalize(root)
            .map(|canonical_root| canonical_path.starts_with(canonical_root))
            .unwrap_or(false)
    })
}

fn ensure_approved(app: &AppHandle, path: &str) -> Result<(), String> {
    let approved = load_approved_roots(app)?;
    if !path_is_within_roots(Path::new(path), &approved) {
        return Err("该路径不在你选择过的项目文件夹内。".to_string());
    }
    Ok(())
}

#[tauri::command]
pub(crate) fn pick_project_folder(app: AppHandle) -> ProjectFolderSelection {
    let selected = app
        .dialog()
        .file()
        .set_title("选择项目文件夹")
        .blocking_pick_folder();

    let path = selected
        .and_then(|file_path| file_path.into_path().ok())
        .map(|path| {
            approve_root(&app, &path);
            path.to_string_lossy().into_owned()
        });

    ProjectFolderSelection { path }
}

fn is_skipped_vcs_or_build_dir(name: &str) -> bool {
    matches!(
        name,
        ".git"
            | "node_modules"
            | ".venv"
            | "venv"
            | "__pycache__"
            | "target"
            | "dist"
            | "build"
            | ".next"
            | ".pytest_cache"
            | ".mypy_cache"
            | ".ruff_cache"
            | ".turbo"
    )
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

fn list_project_folder_impl(path: String) -> ProjectFolderListing {
    let root = Path::new(&path);
    let mut result = ProjectFolderListing {
        path: path.clone(),
        entries: Vec::new(),
        truncated: false,
        error: None,
    };

    let read_dir = match fs::read_dir(root) {
        Ok(read_dir) => read_dir,
        Err(error) => {
            result.error = Some(format!("读取文件夹失败：{error}"));
            return result;
        }
    };

    let mut entries = Vec::new();
    for item in read_dir {
        let entry = match item {
            Ok(entry) => entry,
            Err(_) => continue,
        };
        let name = entry.file_name().to_string_lossy().into_owned();
        let entry_path = entry.path();
        let is_dir = match entry.file_type() {
            Ok(file_type) if file_type.is_dir() => true,
            Ok(file_type) if file_type.is_symlink() => fs::metadata(&entry_path)
                .map(|meta| meta.is_dir())
                .unwrap_or(false),
            _ => false,
        };
        if is_dir && is_skipped_vcs_or_build_dir(&name) {
            continue;
        }
        entries.push(ProjectFolderEntry {
            name,
            path: path_string(&entry_path),
            is_dir,
        });
    }

    entries.sort_by(|left, right| {
        right
            .is_dir
            .cmp(&left.is_dir)
            .then_with(|| left.name.to_lowercase().cmp(&right.name.to_lowercase()))
    });
    result.truncated = entries.len() > MAX_PROJECT_FOLDER_ENTRIES;
    entries.truncate(MAX_PROJECT_FOLDER_ENTRIES);
    result.entries = entries;
    result
}

#[tauri::command]
pub(crate) fn list_project_folder(app: AppHandle, path: String) -> ProjectFolderListing {
    if let Err(error) = ensure_approved(&app, &path) {
        return ProjectFolderListing {
            path,
            entries: Vec::new(),
            truncated: false,
            error: Some(error),
        };
    }
    list_project_folder_impl(path)
}

fn read_project_file_impl(path: String) -> ProjectFileContent {
    let file_path = Path::new(&path);
    let mut result = ProjectFileContent {
        path: path.clone(),
        name: file_path
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_else(|| path.clone()),
        content: None,
        binary: false,
        size: 0,
        error: None,
    };

    let metadata = match fs::metadata(file_path) {
        Ok(metadata) if metadata.is_file() => metadata,
        Ok(_) => {
            result.error = Some("该路径不是文件".to_string());
            return result;
        }
        Err(error) => {
            result.error = Some(format!("读取文件失败：{error}"));
            return result;
        }
    };

    result.size = metadata.len();
    if metadata.len() > MAX_PROJECT_FILE_BYTES {
        result.error = Some("文件超过 1 MiB，暂不在工作台内预览".to_string());
        return result;
    }

    let bytes = match fs::read(file_path) {
        Ok(bytes) => bytes,
        Err(error) => {
            result.error = Some(format!("读取文件失败：{error}"));
            return result;
        }
    };

    let binary = bytes.iter().take(8192).any(|byte| *byte == 0);
    result.binary = binary;
    if binary {
        result.error = Some("二进制文件不支持预览".to_string());
        return result;
    }

    match String::from_utf8(bytes) {
        Ok(content) => {
            result.content = Some(content);
        }
        Err(_) => {
            result.binary = true;
            result.error = Some("文件编码不是 UTF-8，不支持预览".to_string());
        }
    }
    result
}

#[tauri::command]
pub(crate) fn read_project_file(app: AppHandle, path: String) -> ProjectFileContent {
    if let Err(error) = ensure_approved(&app, &path) {
        return ProjectFileContent {
            path,
            name: String::new(),
            content: None,
            binary: false,
            size: 0,
            error: Some(error),
        };
    }
    read_project_file_impl(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_tree() -> (tempfile::TempDir, std::path::PathBuf) {
        let temp = tempfile::tempdir().expect("tempdir");
        let root = temp.path().join("project");
        fs::create_dir_all(root.join("src")).expect("src dir");
        fs::create_dir_all(root.join("node_modules")).expect("node_modules dir");
        fs::write(
            root.join("README.md"),
            "# Demo
",
        )
        .expect("readme");
        fs::write(
            root.join("src/main.py"),
            "print('ok')
",
        )
        .expect("main.py");
        fs::write(root.join("src/blob.bin"), [0_u8, 1, 2]).expect("binary");
        let root_path = root.clone();
        (temp, root_path)
    }

    #[test]
    fn lists_sorted_entries_and_skips_build_dirs() {
        let (_temp, root) = temp_tree();
        let listing = list_project_folder_impl(path_string(&root));
        assert!(listing.error.is_none(), "{:?}", listing.error);
        assert_eq!(
            listing
                .entries
                .iter()
                .map(|entry| entry.name.as_str())
                .collect::<Vec<_>>(),
            vec!["src", "README.md"]
        );
        assert!(listing.entries[0].is_dir);
        assert!(!listing.entries[1].is_dir);
    }

    #[test]
    fn reads_utf8_text_and_rejects_binary_files() {
        let (_temp, root) = temp_tree();
        let readme = read_project_file_impl(path_string(&root.join("README.md")));
        assert_eq!(
            readme.content.as_deref(),
            Some(
                "# Demo
"
            )
        );
        assert!(!readme.binary);

        let binary = read_project_file_impl(path_string(&root.join("src/blob.bin")));
        assert!(binary.binary);
        assert!(binary.content.is_none());
        assert!(binary.error.is_some());
    }

    #[test]
    fn only_accepts_paths_inside_approved_project_roots() {
        let temp = tempfile::tempdir().expect("tempdir");
        let root = temp.path().join("project");
        let outside = temp.path().join("outside");
        fs::create_dir_all(root.join("src")).expect("root");
        fs::create_dir_all(&outside).expect("outside");
        fs::write(
            root.join("README.md"),
            "# Demo
",
        )
        .expect("readme");

        let approved = HashSet::from([root.clone()]);
        assert!(path_is_within_roots(&root.join("src"), &approved));
        assert!(path_is_within_roots(&root.join("README.md"), &approved));
        assert!(!path_is_within_roots(&outside, &approved));
    }

    #[test]
    fn reports_missing_files_without_panicking() {
        let missing = read_project_file_impl("Z:/definitely/not/here.txt".to_string());
        assert!(missing.content.is_none());
        assert!(missing.error.is_some());
    }
}
