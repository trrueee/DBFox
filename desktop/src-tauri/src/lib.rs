use serde::{Deserialize, Serialize};
#[cfg(test)]
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::Manager;

mod sidecar_log;

#[cfg(test)]
use sidecar_log::{redact_sidecar_log_message, SIDECAR_LOG_MAX_MESSAGE_CHARS};
use sidecar_log::{retire_legacy_temp_sidecar_log, SidecarLog};

// build_sidecar.py and the Tauri external-bin contract intentionally publish
// Windows artifacts with the MSVC triplet.  Reject a GNU host explicitly
// instead of producing an installer whose Rust binary and sidecar disagree.
#[cfg(all(target_os = "windows", target_env = "gnu"))]
compile_error!(
    "DBFox Windows desktop builds require the MSVC Rust toolchain (for example: cargo +stable-x86_64-pc-windows-msvc ...)."
);

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Clone)]
struct PythonEngine(Arc<EngineRuntime>);

#[derive(Debug)]
struct EngineRuntime {
    supervisor: Mutex<EngineSupervisor>,
    startup_cancelled: AtomicBool,
}

impl Drop for EngineRuntime {
    fn drop(&mut self) {
        self.startup_cancelled.store(true, Ordering::Release);
        if let Ok(supervisor) = self.supervisor.get_mut() {
            supervisor.stop();
        }
    }
}

impl PythonEngine {
    fn starting() -> Self {
        Self(Arc::new(EngineRuntime {
            supervisor: Mutex::new(EngineSupervisor::starting()),
            startup_cancelled: AtomicBool::new(false),
        }))
    }

    fn start_in_background(&self, log: SidecarLog) {
        let engine = self.clone();
        std::thread::spawn(move || {
            let mut started = EngineSupervisor::start(log, &engine.0.startup_cancelled);
            if engine.0.startup_cancelled.load(Ordering::Acquire) {
                started.stop();
                return;
            }

            let mut current = match engine.0.supervisor.lock() {
                Ok(current) => current,
                Err(_) => {
                    started.stop();
                    return;
                }
            };
            if engine.0.startup_cancelled.load(Ordering::Acquire) {
                started.stop();
                return;
            }
            *current = started;
        });
    }

    fn restart(&self, log: SidecarLog) -> Result<(), String> {
        self.0.startup_cancelled.store(true, Ordering::Release);
        {
            let mut current = self
                .0
                .supervisor
                .lock()
                .map_err(|_| "Engine supervisor lock poisoned".to_string())?;
            current.stop();
            *current = EngineSupervisor::starting();
        }
        self.0.startup_cancelled.store(false, Ordering::Release);
        self.start_in_background(log);
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EngineConfig {
    port: u16,
    token: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum EngineStartupState {
    Starting,
    Ready,
    Failed,
    Stopped,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct EngineStartupStatus {
    state: EngineStartupState,
    error: Option<String>,
}

#[tauri::command]
fn get_engine_config(engine: tauri::State<'_, PythonEngine>) -> Result<EngineConfig, String> {
    let guard = engine
        .0
        .supervisor
        .lock()
        .map_err(|_| "Engine supervisor lock poisoned".to_string())?;
    guard.engine_config()
}

#[tauri::command]
fn get_engine_startup_status(
    engine: tauri::State<'_, PythonEngine>,
) -> Result<EngineStartupStatus, String> {
    let guard = engine
        .0
        .supervisor
        .lock()
        .map_err(|_| "Engine supervisor lock poisoned".to_string())?;
    Ok(guard.startup_status())
}

#[tauri::command]
fn restart_python_engine(
    app: tauri::AppHandle,
    engine: tauri::State<'_, PythonEngine>,
) -> Result<(), String> {
    let log_directory = app
        .path()
        .app_log_dir()
        .map_err(|error| error.to_string())?;
    let sidecar_log = SidecarLog::new(log_directory)?;
    engine.restart(sidecar_log)
}

#[tauri::command]
fn open_diagnostic_logs(app: tauri::AppHandle) -> Result<(), String> {
    let log_directory = app
        .path()
        .app_log_dir()
        .map_err(|error| error.to_string())?;
    std::fs::create_dir_all(&log_directory).map_err(|error| error.to_string())?;

    #[cfg(target_os = "windows")]
    {
        let mut command = Command::new("explorer.exe");
        command.arg(&log_directory);
        return command
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("Failed to open diagnostic log directory: {error}"));
    }
    #[cfg(target_os = "macos")]
    {
        let mut command = Command::new("open");
        command.arg(&log_directory);
        return command
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("Failed to open diagnostic log directory: {error}"));
    }
    #[cfg(target_os = "linux")]
    {
        let mut command = Command::new("xdg-open");
        command.arg(&log_directory);
        return command
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("Failed to open diagnostic log directory: {error}"));
    }

    #[allow(unreachable_code)]
    Err("Opening diagnostic logs is not supported on this platform".to_string())
}

fn generate_random_token() -> String {
    use rand::RngCore;
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}
#[derive(Debug)]
struct EngineSupervisor {
    child: Option<Child>,
    port: Option<u16>,
    token: String,
    state: EngineStartupState,
    error: Option<String>,
}

#[derive(Debug, Deserialize)]
struct EngineReadyPayload {
    port: u16,
}

impl EngineSupervisor {
    fn starting() -> Self {
        Self {
            child: None,
            port: None,
            token: String::new(),
            state: EngineStartupState::Starting,
            error: None,
        }
    }

    fn start(log: SidecarLog, startup_cancelled: &AtomicBool) -> Self {
        let token = generate_random_token();
        let mut supervisor = EngineSupervisor::starting();
        supervisor.token = token.clone();

        if startup_cancelled.load(Ordering::Acquire) {
            supervisor.stop();
            return supervisor;
        }

        let mut child = match spawn_python_engine(&token, &log) {
            Ok(child) => child,
            Err(error) => {
                supervisor.error = Some(error);
                supervisor.state = EngineStartupState::Failed;
                return supervisor;
            }
        };

        if let Some(stderr) = child.stderr.take() {
            drain_engine_pipe(stderr, "stderr", log.clone());
        }

        let stdout = match child.stdout.take() {
            Some(stdout) => stdout,
            None => {
                let error = "Python engine stdout was not captured".to_string();
                log.error(&error);
                stop_engine_child(child);
                supervisor.error = Some(error);
                supervisor.state = EngineStartupState::Failed;
                return supervisor;
            }
        };

        let ready_lines = spawn_stdout_reader(stdout, log.clone());
        match wait_for_engine_ready(
            &mut child,
            ready_lines,
            Duration::from_secs(20),
            startup_cancelled,
        )
        .and_then(|port| {
            wait_for_engine_health(port, Duration::from_secs(20), startup_cancelled).map(|_| port)
        }) {
            Ok(port) => {
                if startup_cancelled.load(Ordering::Acquire) {
                    stop_engine_child(child);
                    supervisor.stop();
                } else {
                    supervisor.port = Some(port);
                    supervisor.state = EngineStartupState::Ready;
                    supervisor.child = Some(child);
                }
            }
            Err(error) => {
                stop_engine_child(child);
                if startup_cancelled.load(Ordering::Acquire) {
                    supervisor.stop();
                } else {
                    log.error(&format!("Python engine failed readiness: {}", error));
                    supervisor.error = Some(error);
                    supervisor.state = EngineStartupState::Failed;
                }
            }
        }

        supervisor
    }

    fn engine_config(&self) -> Result<EngineConfig, String> {
        if self.state == EngineStartupState::Ready {
            if let Some(port) = self.port {
                return Ok(EngineConfig {
                    port,
                    token: self.token.clone(),
                });
            }
        }
        match self.state {
            EngineStartupState::Starting => Err("Python engine is still starting".to_string()),
            EngineStartupState::Failed => Err(self
                .error
                .clone()
                .unwrap_or_else(|| "Python engine failed to start".to_string())),
            EngineStartupState::Stopped => Err("Python engine was stopped".to_string()),
            EngineStartupState::Ready => {
                Err("Python engine is missing its listening port".to_string())
            }
        }
    }

    fn startup_status(&self) -> EngineStartupStatus {
        EngineStartupStatus {
            state: self.state.clone(),
            error: self.error.clone(),
        }
    }

    fn stop(&mut self) {
        if let Some(child) = self.child.take() {
            stop_engine_child(child);
        }
        self.port = None;
        self.state = EngineStartupState::Stopped;
        self.error = None;
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            retire_legacy_temp_sidecar_log().map_err(std::io::Error::other)?;
            let log_directory = app
                .path()
                .app_log_dir()
                .map_err(|error| std::io::Error::other(error.to_string()))?;
            let sidecar_log = SidecarLog::new(log_directory).map_err(std::io::Error::other)?;
            let engine = PythonEngine::starting();
            app.manage(engine.clone());
            engine.start_in_background(sidecar_log);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_engine_config,
            get_engine_startup_status,
            restart_python_engine,
            open_diagnostic_logs
        ])
        .on_window_event(|window, event| {
            if matches!(
                event,
                tauri::WindowEvent::CloseRequested { .. } | tauri::WindowEvent::Destroyed
            ) {
                if let Some(engine) = window.try_state::<PythonEngine>() {
                    stop_python_engine(&engine);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running DBFox");
}
fn stop_python_engine(engine: &PythonEngine) {
    engine.0.startup_cancelled.store(true, Ordering::Release);
    if let Ok(mut guard) = engine.0.supervisor.lock() {
        guard.stop();
    }
}

fn stop_engine_child(mut child: Child) {
    let pid = child.id();

    #[cfg(target_os = "windows")]
    {
        let status = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();

        if status.map(|status| status.success()).unwrap_or(false) {
            let _ = child.wait();
            return;
        }
    }

    let _ = child.kill();
    let _ = child.wait();
}

/// Build the Rust target triplet for the current platform at compile time.
/// This must match the naming convention in `build_sidecar.py:get_target_triplet()`.
fn current_target_triplet() -> &'static str {
    match std::env::consts::OS {
        "windows" => match std::env::consts::ARCH {
            "aarch64" => "aarch64-pc-windows-msvc",
            _ => "x86_64-pc-windows-msvc",
        },
        "macos" => match std::env::consts::ARCH {
            "aarch64" => "aarch64-apple-darwin",
            _ => "x86_64-apple-darwin",
        },
        _ => match std::env::consts::ARCH {
            "aarch64" => "aarch64-unknown-linux-gnu",
            _ => "x86_64-unknown-linux-gnu",
        },
    }
}

fn sidecar_candidate_paths(exe_dir: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    let triplet = current_target_triplet();

    let names: Vec<String> = if cfg!(target_os = "windows") {
        vec![
            "dbfox-engine.exe".into(),
            format!("dbfox-engine-{}.exe", triplet),
        ]
    } else {
        vec!["dbfox-engine".into(), format!("dbfox-engine-{}", triplet)]
    };

    for name in &names {
        candidates.push(exe_dir.join(name));
        candidates.push(exe_dir.join("resources").join(name));
        candidates.push(exe_dir.join("_up_").join("binaries").join(name));
        candidates.push(exe_dir.join("resources").join("binaries").join(name));
        candidates.push(exe_dir.join("binaries").join(name));
    }
    candidates
}

fn parse_engine_ready_line(line: &str) -> Option<u16> {
    let payload = line.strip_prefix("DBFOX_ENGINE_READY")?.trim();
    serde_json::from_str::<EngineReadyPayload>(payload)
        .ok()
        .map(|ready| ready.port)
}

fn spawn_stdout_reader<R>(stdout: R, log: SidecarLog) -> mpsc::Receiver<String>
where
    R: Read + Send + 'static,
{
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            match line {
                Ok(line) => {
                    let _ = tx.send(line);
                }
                Err(error) => {
                    log.error(&format!("Failed reading Python engine stdout: {}", error));
                    break;
                }
            }
        }
    });
    rx
}

fn drain_engine_pipe<R>(pipe: R, stream_name: &'static str, log: SidecarLog)
where
    R: Read + Send + 'static,
{
    std::thread::spawn(move || {
        let reader = BufReader::new(pipe);
        for line in reader.lines() {
            match line {
                Ok(line) => {
                    // The engine already owns redacted diagnostics.  Do not duplicate
                    // raw stdout/stderr here because a third-party library can emit
                    // credential-bearing request context.
                    log.error(&format!(
                        "Python engine {} emitted {} bytes of diagnostic output.",
                        stream_name,
                        line.len()
                    ));
                }
                Err(error) => {
                    log.error(&format!(
                        "Failed reading Python engine {}: {}",
                        stream_name, error
                    ));
                    break;
                }
            }
        }
    });
}

fn wait_for_engine_ready(
    child: &mut Child,
    lines: mpsc::Receiver<String>,
    timeout: Duration,
    startup_cancelled: &AtomicBool,
) -> Result<u16, String> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if startup_cancelled.load(Ordering::Acquire) {
            return Err("Python engine startup was cancelled".to_string());
        }
        match lines.recv_timeout(Duration::from_millis(100)) {
            Ok(line) => {
                if let Some(port) = parse_engine_ready_line(&line) {
                    return Ok(port);
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                if let Ok(Some(status)) = child.try_wait() {
                    return Err(format!("Python engine exited before ready: {}", status));
                }
            }
        }

        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("Python engine exited before ready: {}", status));
        }
    }
    Err("Timed out waiting for Python engine ready line".to_string())
}

fn wait_for_engine_health(
    port: u16,
    timeout: Duration,
    startup_cancelled: &AtomicBool,
) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    let mut last_error = "health endpoint was not reachable".to_string();
    while Instant::now() < deadline {
        if startup_cancelled.load(Ordering::Acquire) {
            return Err("Python engine startup was cancelled".to_string());
        }
        match probe_engine_health(port) {
            Ok(()) => return Ok(()),
            Err(error) => last_error = error,
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    Err(last_error)
}

fn probe_engine_health(port: u16) -> Result<(), String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(500))
        .map_err(|error| format!("connect failed: {}", error))?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    stream
        .write_all(b"GET /api/v1/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .map_err(|error| format!("health request write failed: {}", error))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("health response read failed: {}", error))?;

    if (response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200"))
        && response.contains("\"healthy\"")
    {
        Ok(())
    } else {
        Err("health endpoint did not return healthy status".to_string())
    }
}

fn python_dev_engine_args() -> [&'static str; 3] {
    ["-m", "engine.main", "--no-reload"]
}

fn spawn_python_engine(token: &str, log: &SidecarLog) -> Result<Child, String> {
    if cfg!(debug_assertions) {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .to_path_buf();
        match Command::new("python")
            .args(python_dev_engine_args())
            .env("PYTHONPATH", &root)
            .env("DBFOX_ENGINE_PORT", "0")
            .env("DBFOX_ENGINE_TOKEN", token)
            .current_dir(&root)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(child) => {
                println!("DBFox Python Engine (Dev) started (pid: {})", child.id());
                Ok(child)
            }
            Err(e) => {
                let error = format!("Failed to start Python Dev engine: {}", e);
                log.error(&error);
                Err(error)
            }
        }
    } else {
        // Production Mode: Spawn the sidecar binary directly
        let exe_path = match std::env::current_exe() {
            Ok(path) => path,
            Err(e) => {
                let error = format!("Unable to resolve current exe path: {}", e);
                log.error(&error);
                return Err(error);
            }
        };
        let exe_dir = match exe_path.parent() {
            Some(dir) => dir,
            None => {
                let error = "Unable to resolve exe parent directory".to_string();
                log.error(&error);
                return Err(error);
            }
        };

        let candidates = sidecar_candidate_paths(exe_dir);
        let sidecar_path = candidates.iter().find(|path| path.exists()).cloned();

        let final_path = sidecar_path.unwrap_or_else(|| candidates[0].clone());

        match Command::new(&final_path)
            .env("DBFOX_ENGINE_PORT", "0")
            .env("DBFOX_ENGINE_TOKEN", token)
            .current_dir(exe_dir)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(child) => {
                println!("DBFox Sidecar Engine (Prod) started (pid: {})", child.id());
                Ok(child)
            }
            Err(e) => {
                let error = format!("Failed to start Sidecar Engine at {:?}: {}", final_path, e);
                log.error(&error);
                Err(error)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_log_directory(label: &str) -> PathBuf {
        let nonce = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system clock should be after the Unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("dbfox-sidecar-log-test-{}-{}", label, nonce))
    }

    #[test]
    fn sidecar_candidates_include_generic_binary_next_to_app() {
        let exe_dir = PathBuf::from(r"C:\DBFox");
        let candidates = sidecar_candidate_paths(&exe_dir);

        assert!(candidates.contains(&exe_dir.join("dbfox-engine.exe")));
    }

    #[test]
    fn sidecar_candidates_include_current_target_triplet() {
        let exe_dir = PathBuf::from(r"C:\DBFox");
        let candidates = sidecar_candidate_paths(&exe_dir);
        let triplet = current_target_triplet();
        let expected_name = if cfg!(target_os = "windows") {
            format!("dbfox-engine-{}.exe", triplet)
        } else {
            format!("dbfox-engine-{}", triplet)
        };

        assert!(
            candidates.contains(&exe_dir.join(&expected_name)),
            "Missing triplet binary: {}",
            expected_name
        );
    }

    #[test]
    fn parses_engine_ready_stdout_line() {
        let line = r#"DBFOX_ENGINE_READY {"port":18731}"#;

        assert_eq!(parse_engine_ready_line(line), Some(18731));
    }

    #[test]
    fn ignores_non_ready_stdout_line() {
        assert_eq!(
            parse_engine_ready_line("INFO: started server process"),
            None
        );
    }

    #[test]
    fn dev_engine_args_disable_python_reload() {
        assert_eq!(
            python_dev_engine_args(),
            ["-m", "engine.main", "--no-reload"]
        );
    }

    #[test]
    fn supervisor_returns_config_only_when_ready() {
        let supervisor = EngineSupervisor {
            child: None,
            port: Some(18731),
            token: "test-token".to_string(),
            state: EngineStartupState::Ready,
            error: None,
        };

        let config = supervisor
            .engine_config()
            .expect("ready supervisor should expose config");
        assert_eq!(config.port, 18731);
        assert_eq!(config.token, "test-token");
    }

    #[test]
    fn supervisor_exposes_starting_and_stopped_lifecycle_states() {
        let mut supervisor = EngineSupervisor::starting();
        assert_eq!(
            supervisor.startup_status().state,
            EngineStartupState::Starting
        );
        assert!(supervisor.engine_config().is_err());

        supervisor.stop();
        assert_eq!(
            supervisor.startup_status().state,
            EngineStartupState::Stopped
        );
        assert!(supervisor.engine_config().is_err());
    }

    #[test]
    fn sidecar_log_redacts_sensitive_content_and_rotates() {
        let directory = test_log_directory("redact-rotate");
        let log = SidecarLog::with_limits(directory.clone(), 1, 1)
            .expect("test sidecar log directory should be creatable");

        log.error("safe startup diagnostic");
        log.error("token=must-not-be-persisted");

        let current = fs::read_to_string(log.log_path()).expect("current log should exist");
        let backup = fs::read_to_string(log.log_path().with_extension("log.1"))
            .expect("rotated backup should exist");
        assert!(current.contains("[REDACTED sidecar diagnostic"));
        assert!(backup.contains("safe startup diagnostic"));
        assert!(!current.contains("must-not-be-persisted"));
        assert!(!backup.contains("must-not-be-persisted"));

        fs::remove_dir_all(directory).expect("test sidecar log directory should be removable");
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
