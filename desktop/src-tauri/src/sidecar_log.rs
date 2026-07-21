use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

const SIDECAR_LOG_FILE_NAME: &str = "dbfox-sidecar.log";
const SIDECAR_LOG_MAX_BYTES: u64 = 2 * 1024 * 1024;
const SIDECAR_LOG_BACKUP_COUNT: usize = 3;
pub(crate) const SIDECAR_LOG_MAX_MESSAGE_CHARS: usize = 2048;

/// Bounded, redacted diagnostics for the Python sidecar process.
#[derive(Clone, Debug)]
pub(crate) struct SidecarLog {
    directory: PathBuf,
    max_bytes: u64,
    backup_count: usize,
    write_lock: Arc<Mutex<()>>,
}

impl SidecarLog {
    pub(crate) fn new(directory: PathBuf) -> Result<Self, String> {
        Self::with_limits(directory, SIDECAR_LOG_MAX_BYTES, SIDECAR_LOG_BACKUP_COUNT)
    }

    pub(crate) fn with_limits(
        directory: PathBuf,
        max_bytes: u64,
        backup_count: usize,
    ) -> Result<Self, String> {
        fs::create_dir_all(&directory).map_err(|error| {
            format!(
                "Failed to create DBFox sidecar log directory {}: {}",
                directory.display(),
                error
            )
        })?;
        Ok(Self {
            directory,
            max_bytes,
            backup_count,
            write_lock: Arc::new(Mutex::new(())),
        })
    }

    pub(crate) fn log_path(&self) -> PathBuf {
        self.directory.join(SIDECAR_LOG_FILE_NAME)
    }

    pub(crate) fn error(&self, message: &str) {
        let safe_message = redact_sidecar_log_message(message);
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_secs().to_string())
            .unwrap_or_default();
        let entry = format!("[{}] {}\n", ts, safe_message);

        if let Ok(_guard) = self.write_lock.lock() {
            let path = self.log_path();
            if let Err(error) = self.rotate_if_needed(&path) {
                eprintln!("Failed to rotate DBFox sidecar log: {}", error);
            }
            if let Err(error) = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&path)
                .and_then(|mut file| file.write_all(entry.as_bytes()))
            {
                eprintln!("Failed to write DBFox sidecar log: {}", error);
            }
        }
        eprintln!("{}", safe_message);
    }

    fn rotate_if_needed(&self, path: &Path) -> std::io::Result<()> {
        if !path.exists() || fs::metadata(path)?.len() < self.max_bytes {
            return Ok(());
        }

        for index in (1..=self.backup_count).rev() {
            let destination = path.with_extension(format!("log.{}", index));
            if destination.exists() {
                fs::remove_file(&destination)?;
            }
            let source = if index == 1 {
                path.to_path_buf()
            } else {
                path.with_extension(format!("log.{}", index - 1))
            };
            if source.exists() {
                fs::rename(source, destination)?;
            }
        }
        Ok(())
    }
}

pub(crate) fn redact_sidecar_log_message(message: &str) -> String {
    let lowered = message.to_ascii_lowercase();
    const SENSITIVE_MARKERS: [&str; 11] = [
        "api_key",
        "api-key",
        "authorization",
        "bearer ",
        "cookie",
        "password",
        "secret",
        "token",
        "connection_string",
        "dsn=",
        "://",
    ];
    if SENSITIVE_MARKERS
        .iter()
        .any(|marker| lowered.contains(marker))
    {
        return "[REDACTED sidecar diagnostic containing sensitive-looking data]".to_string();
    }

    let bounded: String = message
        .trim()
        .chars()
        .take(SIDECAR_LOG_MAX_MESSAGE_CHARS)
        .collect();
    if message.trim().chars().count() > SIDECAR_LOG_MAX_MESSAGE_CHARS {
        format!("{}… [truncated]", bounded)
    } else {
        bounded
    }
}

/// Remove the fixed legacy host log without following links.
pub(crate) fn retire_legacy_temp_sidecar_log() -> Result<(), String> {
    let path = std::env::temp_dir().join(SIDECAR_LOG_FILE_NAME);
    let metadata = match fs::symlink_metadata(&path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => {
            return Err(format!(
                "Failed to inspect legacy DBFox sidecar log {}: {}",
                path.display(),
                error
            ));
        }
    };
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(format!(
            "Refusing to remove non-regular legacy DBFox sidecar log {}",
            path.display()
        ));
    }
    fs::remove_file(&path).map_err(|error| {
        format!(
            "Failed to remove legacy DBFox sidecar log {}: {}",
            path.display(),
            error
        )
    })
}
