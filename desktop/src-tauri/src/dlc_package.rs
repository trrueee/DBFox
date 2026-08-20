use serde::Serialize;
use std::path::Path;
use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct DlcPackageSelection {
    path: Option<String>,
}

fn is_dlc_package_file(path: &Path) -> bool {
    path.is_file()
        && path
            .extension()
            .and_then(|extension| extension.to_str())
            .is_some_and(|extension| extension.eq_ignore_ascii_case("dbfox-dlc"))
}

#[tauri::command]
pub(crate) async fn pick_dlc_package(app: AppHandle) -> Result<DlcPackageSelection, String> {
    let selected = app
        .dialog()
        .file()
        .set_title("选择 DBFox DLC 安装包")
        .add_filter("DBFox DLC Package", &["dbfox-dlc"])
        .blocking_pick_file();

    let Some(selected) = selected else {
        return Ok(DlcPackageSelection { path: None });
    };
    let path = selected
        .into_path()
        .map_err(|_| "选择的 DLC 路径不是本机文件路径".to_string())?;
    if !is_dlc_package_file(&path) {
        return Err("只能选择现有的 .dbfox-dlc 单文件安装包".to_string());
    }
    let path = path
        .to_str()
        .ok_or_else(|| "选择的 DLC 路径不是有效 Unicode 文件路径".to_string())?;
    Ok(DlcPackageSelection {
        path: Some(path.to_string()),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_only_existing_single_file_dlc_packages() {
        let temp = tempfile::tempdir().expect("tempdir");
        let package = temp.path().join("acme.echo.dbfox-dlc");
        std::fs::write(&package, b"fixture").expect("package");
        let uppercase = temp.path().join("ACME.DBFOX-DLC");
        std::fs::write(&uppercase, b"fixture").expect("uppercase package");
        let archive = temp.path().join("acme.echo.zip");
        std::fs::write(&archive, b"fixture").expect("archive");
        let directory = temp.path().join("fake.dbfox-dlc");
        std::fs::create_dir(&directory).expect("directory");

        assert!(is_dlc_package_file(&package));
        assert!(is_dlc_package_file(&uppercase));
        assert!(!is_dlc_package_file(&archive));
        assert!(!is_dlc_package_file(&directory));
        assert!(!is_dlc_package_file(&temp.path().join("missing.dbfox-dlc")));
    }
}
