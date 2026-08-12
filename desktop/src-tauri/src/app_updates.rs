use serde::Serialize;
use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, Manager};
use tauri_plugin_updater::{Update, UpdaterExt};

use crate::crash_recovery::CrashRecoveryState;
use crate::{stop_python_engine, PythonEngine};

const UPDATE_TIMEOUT: Duration = Duration::from_secs(30);
const UPDATE_CHANNEL: &str = "stable";
const UPDATER_ENABLED: bool = !cfg!(debug_assertions);

#[derive(Default)]
pub(crate) struct PendingUpdate(Mutex<Option<Update>>);

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateConfiguration {
    configured: bool,
    channel: &'static str,
    current_version: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateCheckResult {
    available: bool,
    current_version: String,
    version: Option<String>,
    body: Option<String>,
    published_at_unix: Option<i64>,
}

#[tauri::command]
pub(crate) fn get_update_configuration(app: AppHandle) -> UpdateConfiguration {
    UpdateConfiguration {
        configured: UPDATER_ENABLED,
        channel: UPDATE_CHANNEL,
        current_version: app.package_info().version.to_string(),
    }
}

#[tauri::command]
pub(crate) async fn check_for_app_update(
    app: AppHandle,
    pending: tauri::State<'_, PendingUpdate>,
) -> Result<UpdateCheckResult, String> {
    if !UPDATER_ENABLED {
        return Err("此构建未配置签名更新通道。".to_string());
    }
    let engine = app.state::<PythonEngine>().inner().clone();
    let app_for_exit = app.clone();
    let updater = app
        .updater_builder()
        .timeout(UPDATE_TIMEOUT)
        .on_before_exit(move || {
            stop_python_engine(&engine);
            if let Some(recovery) = app_for_exit.try_state::<CrashRecoveryState>() {
                recovery.clear();
            }
            app_for_exit.cleanup_before_exit();
        })
        .build()
        .map_err(|error| safe_updater_error("build", error))?;
    let update = updater
        .check()
        .await
        .map_err(|error| safe_updater_error("check", error))?;
    let current_version = app.package_info().version.to_string();

    let Some(update) = update else {
        *pending
            .0
            .lock()
            .map_err(|_| "更新状态暂时不可用。".to_string())? = None;
        return Ok(UpdateCheckResult {
            available: false,
            current_version,
            version: None,
            body: None,
            published_at_unix: None,
        });
    };

    let result = UpdateCheckResult {
        available: true,
        current_version,
        version: Some(update.version.clone()),
        body: update.body.clone(),
        published_at_unix: update.date.map(|date| date.unix_timestamp()),
    };
    *pending
        .0
        .lock()
        .map_err(|_| "更新状态暂时不可用。".to_string())? = Some(update);
    Ok(result)
}

#[tauri::command]
pub(crate) async fn install_pending_app_update(
    pending: tauri::State<'_, PendingUpdate>,
) -> Result<(), String> {
    let update = pending
        .0
        .lock()
        .map_err(|_| "更新状态暂时不可用。".to_string())?
        .take()
        .ok_or_else(|| "没有已检查并可安装的更新。".to_string())?;

    if let Err(error) = update.download_and_install(|_, _| {}, || {}).await {
        if let Ok(mut slot) = pending.0.lock() {
            *slot = Some(update);
        }
        return Err(safe_updater_error("install", error));
    }
    Ok(())
}

fn safe_updater_error(operation: &str, error: tauri_plugin_updater::Error) -> String {
    log::error!("updater {operation} failed: {error}");
    "无法完成更新操作，请检查网络后重试或查看诊断日志。".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tauri_updater_configuration_satisfies_official_plugin_contract() {
        let root: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).expect("valid Tauri config");
        let updater = root
            .pointer("/plugins/updater")
            .cloned()
            .expect("plugins.updater must be an object, never null");
        let config: tauri_plugin_updater::Config =
            serde_json::from_value(updater).expect("valid official updater plugin config");

        assert!(!config.pubkey.trim().is_empty());
        assert_eq!(config.endpoints.len(), 1);
        assert!(config.endpoints[0].as_str().starts_with("https://"));
        assert_eq!(UPDATE_CHANNEL, "stable");
    }
}
