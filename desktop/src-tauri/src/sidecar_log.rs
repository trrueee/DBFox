use std::fs;

const SIDECAR_LOG_FILE_NAME: &str = "dbfox-sidecar.log";
pub(crate) const SIDECAR_LOG_MAX_MESSAGE_CHARS: usize = 2048;
pub(crate) const SIDECAR_LOG_TARGET: &str = "dbfox::sidecar";

/// Bounded, redacted diagnostics for the Python sidecar process.
///
/// Tauri's log plugin owns file creation, synchronization and rotation. DBFox
/// owns only the product-specific event schema and secret redaction policy.
#[derive(Clone, Copy, Debug, Default)]
pub(crate) struct SidecarLog;

impl SidecarLog {
    pub(crate) fn error(&self, message: &str) {
        self.event(log::Level::Error, "host.error", message);
    }

    pub(crate) fn info(&self, event: &str, message: &str) {
        self.event(log::Level::Info, event, message);
    }

    pub(crate) fn event(&self, level: log::Level, event: &str, message: &str) {
        let entry = format_sidecar_log_event(level, event, message);
        log::log!(target: SIDECAR_LOG_TARGET, level, "{entry}");
    }
}

fn format_sidecar_log_event(level: log::Level, event: &str, message: &str) -> String {
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or_default();
    serde_json::json!({
        "timestampUnix": timestamp,
        "level": level.to_string().to_ascii_lowercase(),
        "component": "desktop-host",
        "event": event,
        "message": redact_sidecar_log_message(message),
    })
    .to_string()
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sidecar_log_event_is_structured_and_redacted_before_dispatch() {
        let entry = format_sidecar_log_event(
            log::Level::Error,
            "sidecar.failed",
            "token=must-not-be-persisted",
        );
        let value: serde_json::Value = serde_json::from_str(&entry).expect("JSON log event");

        assert_eq!(value["level"], "error");
        assert_eq!(value["component"], "desktop-host");
        assert_eq!(value["event"], "sidecar.failed");
        assert!(value["message"]
            .as_str()
            .expect("message")
            .contains("[REDACTED"));
        assert!(!entry.contains("must-not-be-persisted"));
    }

    #[test]
    fn sidecar_log_redacts_urls_and_bounds_non_sensitive_messages() {
        assert_eq!(
            redact_sidecar_log_message("https://example.invalid/request"),
            "[REDACTED sidecar diagnostic containing sensitive-looking data]"
        );
        let oversized = "x".repeat(SIDECAR_LOG_MAX_MESSAGE_CHARS + 1);
        assert!(redact_sidecar_log_message(&oversized).ends_with("… [truncated]"));
    }
}
