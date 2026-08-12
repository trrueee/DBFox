use serde::Serialize;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::{AppHandle, Manager};

const SESSION_MARKER_FILE: &str = "session-active-v1";

pub(crate) struct CrashRecoveryState {
    marker_path: PathBuf,
    previous_unclean_exit: bool,
    cleared: AtomicBool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LaunchRecoveryStatus {
    previous_unclean_exit: bool,
}

impl CrashRecoveryState {
    pub(crate) fn initialize(app: &AppHandle) -> io::Result<Self> {
        let marker_path = app
            .path()
            .app_data_dir()
            .map_err(io::Error::other)?
            .join(SESSION_MARKER_FILE);
        let previous_unclean_exit = marker_path.exists();
        write_marker(&marker_path)?;
        Ok(Self {
            marker_path,
            previous_unclean_exit,
            cleared: AtomicBool::new(false),
        })
    }

    pub(crate) fn clear(&self) {
        if self.cleared.swap(true, Ordering::AcqRel) {
            return;
        }
        if let Err(error) = remove_marker(&self.marker_path) {
            log::warn!("failed to clear session marker: {error}");
        }
    }

    fn status(&self) -> LaunchRecoveryStatus {
        LaunchRecoveryStatus {
            previous_unclean_exit: self.previous_unclean_exit,
        }
    }
}

#[tauri::command]
pub(crate) fn get_launch_recovery_status(
    state: tauri::State<'_, CrashRecoveryState>,
) -> LaunchRecoveryStatus {
    state.status()
}

fn write_marker(path: &Path) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, b"active\n")
}

fn remove_marker(path: &Path) -> io::Result<()> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn marker_distinguishes_active_and_graceful_sessions() {
        let nonce = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "dbfox-crash-recovery-{}-{nonce}",
            std::process::id(),
        ));
        let marker = root.join(SESSION_MARKER_FILE);
        remove_marker(&marker).unwrap();

        assert!(!marker.exists());
        write_marker(&marker).unwrap();
        assert!(marker.exists());
        remove_marker(&marker).unwrap();
        assert!(!marker.exists());

        let _ = fs::remove_dir_all(root);
    }
}
