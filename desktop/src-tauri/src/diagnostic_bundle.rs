use regex::{Captures, Regex};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use std::time::{SystemTime, UNIX_EPOCH};
use zip::write::SimpleFileOptions;
#[cfg(test)]
use zip::ZipArchive;
use zip::{CompressionMethod, ZipWriter};

const MAX_INPUT_BYTES: usize = 1024 * 1024;
const MAX_STRING_CHARS: usize = 64 * 1024;
const MAX_HOST_LOG_BYTES: usize = 256 * 1024;
const MAX_DEPTH: usize = 16;

static ASSIGNMENT_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?i)(["']?\b(?:api[_-]?key|admin[_-]?api[_-]?key|openai[_-]?api[_-]?key|aliyun[_-]?api[_-]?key|password|passwd|pwd|secret|token|cookie|connection[_-]?string|dsn)\b["']?\s*[:=]\s*)(["']?)([^"'\s,;}\]]+)(["']?)"#)
        .expect("diagnostic assignment regex must compile")
});
static AUTHORIZATION_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)\b(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)")
        .expect("authorization regex must compile")
});
static URL_PASSWORD_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(://[^:/@\s]+:)([^@/\s]+)(@)").expect("URL password regex must compile")
});

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct DiagnosticBundlePayload {
    pub(crate) engine_snapshot: Value,
    pub(crate) webview_snapshot: Value,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct HostDiagnosticSnapshot {
    pub(crate) app_version: String,
    pub(crate) os: String,
    pub(crate) arch: String,
    pub(crate) engine_state: String,
    pub(crate) engine_generation: u64,
    pub(crate) engine_restart_count: u32,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct DiagnosticBundleResult {
    pub(crate) path: String,
    pub(crate) size_bytes: u64,
    pub(crate) created_at_unix: u64,
}

pub(crate) fn export_bundle(
    log_directory: &Path,
    payload: DiagnosticBundlePayload,
    host: HostDiagnosticSnapshot,
) -> Result<DiagnosticBundleResult, String> {
    let engine = sanitize_snapshot(payload.engine_snapshot)?;
    let webview = sanitize_snapshot(payload.webview_snapshot)?;
    let created_at_unix = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let bundle_directory = log_directory.join("diagnostic-bundles");
    fs::create_dir_all(&bundle_directory).map_err(|error| error.to_string())?;
    let nonce: u64 = rand::random();
    let filename = format!("dbfox-diagnostics-{created_at_unix}-{nonce:016x}.zip");
    let final_path = bundle_directory.join(filename);
    let temporary_path = final_path.with_extension("zip.tmp");

    let result = write_bundle(
        &temporary_path,
        log_directory,
        created_at_unix,
        &host,
        &engine,
        &webview,
    );
    if let Err(error) = result {
        let _ = fs::remove_file(&temporary_path);
        return Err(error);
    }
    fs::rename(&temporary_path, &final_path).map_err(|error| {
        let _ = fs::remove_file(&temporary_path);
        format!("Failed to publish diagnostic bundle: {error}")
    })?;
    let size_bytes = fs::metadata(&final_path)
        .map_err(|error| error.to_string())?
        .len();
    Ok(DiagnosticBundleResult {
        path: final_path.to_string_lossy().into_owned(),
        size_bytes,
        created_at_unix,
    })
}

fn write_bundle(
    path: &Path,
    log_directory: &Path,
    created_at_unix: u64,
    host: &HostDiagnosticSnapshot,
    engine: &Value,
    webview: &Value,
) -> Result<(), String> {
    let file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .map_err(|error| format!("Failed to create diagnostic bundle: {error}"))?;
    let mut zip = ZipWriter::new(file);
    let options = SimpleFileOptions::default()
        .compression_method(CompressionMethod::Stored)
        .unix_permissions(0o600);
    let manifest = serde_json::json!({
        "schemaVersion": 1,
        "createdAtUnix": created_at_unix,
        "host": host,
        "policy": {
            "redacted": true,
            "maxSnapshotBytes": MAX_INPUT_BYTES,
            "maxHostLogBytes": MAX_HOST_LOG_BYTES,
            "excluded": ["credentials", "local engine token", "database contents", "query result rows"]
        }
    });
    write_json(&mut zip, "manifest.json", &manifest, options)?;
    write_json(&mut zip, "engine.json", engine, options)?;
    write_json(&mut zip, "webview.json", webview, options)?;

    for base_name in ["dbfox-sidecar", "dbfox-host"] {
        for (filename, source) in diagnostic_log_files(log_directory, base_name)? {
            if let Some(content) = read_regular_log(&source)? {
                zip.start_file(format!("host/{filename}"), options)
                    .map_err(|error| error.to_string())?;
                zip.write_all(redact_text(&content).as_bytes())
                    .map_err(|error| error.to_string())?;
            }
        }
    }
    zip.finish().map_err(|error| error.to_string())?;
    Ok(())
}

fn diagnostic_log_files(
    log_directory: &Path,
    base_name: &str,
) -> Result<Vec<(String, PathBuf)>, String> {
    let active_name = format!("{base_name}.log");
    let rotated_prefix = format!("{base_name}_");
    let mut files = fs::read_dir(log_directory)
        .map_err(|error| error.to_string())?
        .filter_map(Result::ok)
        .filter_map(|entry| {
            let name = entry.file_name().to_string_lossy().into_owned();
            (name == active_name || (name.starts_with(&rotated_prefix) && name.ends_with(".log")))
                .then_some((name, entry.path()))
        })
        .collect::<Vec<_>>();
    files.sort_by(
        |left, right| match (left.0 == active_name, right.0 == active_name) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => right.0.cmp(&left.0),
        },
    );
    files.truncate(4);
    Ok(files)
}

fn write_json(
    zip: &mut ZipWriter<File>,
    name: &str,
    value: &Value,
    options: SimpleFileOptions,
) -> Result<(), String> {
    let bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    zip.start_file(name, options)
        .map_err(|error| error.to_string())?;
    zip.write_all(&bytes).map_err(|error| error.to_string())
}

fn read_regular_log(path: &Path) -> Result<Option<String>, String> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.to_string()),
    };
    if !metadata.file_type().is_file() {
        return Ok(None);
    }
    let mut file = File::open(path).map_err(|error| error.to_string())?;
    if metadata.len() > MAX_HOST_LOG_BYTES as u64 {
        use std::io::{Seek, SeekFrom};
        file.seek(SeekFrom::End(-(MAX_HOST_LOG_BYTES as i64)))
            .map_err(|error| error.to_string())?;
    }
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)
        .map_err(|error| error.to_string())?;
    Ok(Some(String::from_utf8_lossy(&bytes).into_owned()))
}

fn sanitize_snapshot(value: Value) -> Result<Value, String> {
    let sanitized = sanitize_value(value, 0);
    let size = serde_json::to_vec(&sanitized)
        .map_err(|error| error.to_string())?
        .len();
    if size > MAX_INPUT_BYTES {
        return Err(format!(
            "Diagnostic snapshot exceeds {MAX_INPUT_BYTES} bytes"
        ));
    }
    Ok(sanitized)
}

fn sanitize_value(value: Value, depth: usize) -> Value {
    if depth >= MAX_DEPTH {
        return Value::String("[Maximum diagnostic depth reached]".to_string());
    }
    match value {
        Value::String(text) => Value::String(redact_text(&text)),
        Value::Array(items) => Value::Array(
            items
                .into_iter()
                .take(2_000)
                .map(|item| sanitize_value(item, depth + 1))
                .collect(),
        ),
        Value::Object(items) => {
            let mut sanitized = Map::new();
            for (key, child) in items.into_iter().take(1_000) {
                let value = if sensitive_key(&key) {
                    Value::String("[REDACTED]".to_string())
                } else {
                    sanitize_value(child, depth + 1)
                };
                sanitized.insert(key, value);
            }
            Value::Object(sanitized)
        }
        other => other,
    }
}

fn sensitive_key(key: &str) -> bool {
    let key = key.to_ascii_lowercase().replace('-', "_");
    [
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "authorization",
        "cookie",
        "connection_string",
        "dsn",
    ]
    .iter()
    .any(|marker| key == *marker || key.ends_with(&format!("_{marker}")))
}

fn redact_text(text: &str) -> String {
    let bounded: String = text.chars().take(MAX_STRING_CHARS).collect();
    let redacted = URL_PASSWORD_RE.replace_all(&bounded, "$1[REDACTED]$3");
    let redacted = AUTHORIZATION_RE.replace_all(&redacted, |captures: &Captures<'_>| {
        format!(
            "{}{}[REDACTED]",
            captures.get(1).map_or("", |value| value.as_str()),
            captures.get(2).map_or("", |value| value.as_str()),
        )
    });
    ASSIGNMENT_RE
        .replace_all(&redacted, |captures: &Captures<'_>| {
            format!(
                "{}{}[REDACTED]{}",
                captures.get(1).map_or("", |value| value.as_str()),
                captures.get(2).map_or("", |value| value.as_str()),
                captures.get(4).map_or("", |value| value.as_str()),
            )
        })
        .into_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn redaction_contract() -> Value {
        serde_json::from_str(include_str!(
            "../../../test-fixtures/redaction-contract.json"
        ))
        .expect("shared redaction contract must be valid JSON")
    }

    #[test]
    fn rust_redaction_satisfies_shared_cross_language_contract() {
        let contract = redaction_contract();
        for case in contract["textCases"].as_array().expect("text cases") {
            let redacted = redact_text(case["input"].as_str().expect("text input"));
            for forbidden in case["forbidden"].as_array().expect("forbidden") {
                assert!(
                    !redacted.contains(forbidden.as_str().expect("forbidden string")),
                    "{}",
                    case["id"]
                );
            }
            for required in case["required"].as_array().expect("required") {
                assert!(
                    redacted.contains(required.as_str().expect("required string")),
                    "{}",
                    case["id"]
                );
            }
        }
        for case in contract["structuredCases"]
            .as_array()
            .expect("structured cases")
        {
            let sanitized = sanitize_snapshot(case["input"].clone()).expect("sanitized fixture");
            let serialized = serde_json::to_string(&sanitized).expect("serialized fixture");
            for forbidden in case["forbidden"].as_array().expect("forbidden") {
                assert!(!serialized.contains(forbidden.as_str().expect("forbidden string")));
            }
            for required in case["required"].as_array().expect("required") {
                assert!(serialized.contains(required.as_str().expect("required string")));
            }
        }
    }

    #[test]
    fn rust_redaction_bounds_recursive_equivalent_and_oversized_input() {
        let contract = redaction_contract();
        let recursive = &contract["recursiveCase"];
        let mut value = serde_json::json!({
            "safe": recursive["safeValue"].clone(),
            "token": recursive["secretValue"].clone(),
        });
        for _ in 0..recursive["depth"].as_u64().expect("depth") {
            value = serde_json::json!({"next": value});
        }
        let sanitized = sanitize_snapshot(value).expect("deep JSON is bounded by maximum depth");
        let serialized = serde_json::to_string(&sanitized).expect("deep JSON output");
        assert!(serialized.contains("Maximum diagnostic depth reached"));
        assert!(!serialized.contains(recursive["secretValue"].as_str().expect("secret")));

        let oversized = &contract["oversizedCase"];
        let content = format!(
            "{}{}",
            oversized["prefix"].as_str().expect("prefix"),
            oversized["fill"]
                .as_str()
                .expect("fill")
                .repeat(oversized["repeat"].as_u64().expect("repeat") as usize)
        );
        assert!(sanitize_snapshot(Value::String(content)).is_ok());
    }

    #[test]
    fn bundle_redacts_snapshots_and_host_logs() {
        let directory =
            std::env::temp_dir().join(format!("dbfox-diagnostic-bundle-{}", rand::random::<u64>()));
        fs::create_dir_all(&directory).expect("test directory");
        fs::write(
            directory.join("dbfox-sidecar.log"),
            "authorization: Bearer host-secret\nhealthy\n",
        )
        .expect("host log");
        fs::write(
            directory.join("dbfox-sidecar_2026-08-03_22-40-00.log"),
            "password=rotated-secret\nrotated healthy\n",
        )
        .expect("rotated sidecar log");
        fs::write(
            directory.join("dbfox-sidecar.log.1"),
            "legacy-file-must-not-be-collected\n",
        )
        .expect("legacy unmanaged log");
        let result = export_bundle(
            &directory,
            DiagnosticBundlePayload {
                engine_snapshot: serde_json::json!({"password": "engine-secret", "ok": true}),
                webview_snapshot: serde_json::json!({"content": "api_key=web-secret"}),
            },
            HostDiagnosticSnapshot {
                app_version: "test".to_string(),
                os: "test".to_string(),
                arch: "test".to_string(),
                engine_state: "ready".to_string(),
                engine_generation: 2,
                engine_restart_count: 0,
            },
        )
        .expect("bundle export");

        let file = File::open(&result.path).expect("bundle file");
        let mut archive = ZipArchive::new(file).expect("zip archive");
        for name in [
            "engine.json",
            "webview.json",
            "host/dbfox-sidecar.log",
            "host/dbfox-sidecar_2026-08-03_22-40-00.log",
        ] {
            let mut entry = archive.by_name(name).expect("bundle entry");
            let mut content = String::new();
            entry.read_to_string(&mut content).expect("entry text");
            assert!(content.contains("[REDACTED]"));
            assert!(!content.contains("engine-secret"));
            assert!(!content.contains("web-secret"));
            assert!(!content.contains("host-secret"));
            assert!(!content.contains("rotated-secret"));
        }
        assert!(archive.by_name("host/dbfox-sidecar.log.1").is_err());
        fs::remove_dir_all(directory).expect("cleanup test bundle");
    }
}
