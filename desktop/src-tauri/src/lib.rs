use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
#[cfg(test)]
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager};

mod diagnostic_bundle;
mod sidecar_log;

use diagnostic_bundle::{
    export_bundle, DiagnosticBundlePayload, DiagnosticBundleResult, HostDiagnosticSnapshot,
};
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
    shutting_down: AtomicBool,
    epoch: AtomicU64,
    next_generation: AtomicU64,
    restart_history: Mutex<VecDeque<Instant>>,
    monitor_started: AtomicBool,
}

const ENGINE_PROTOCOL_VERSION: u16 = 1;
const ENGINE_RESTART_LIMIT: usize = 3;
const ENGINE_RESTART_WINDOW: Duration = Duration::from_secs(60);
const ENGINE_EXIT_POLL_INTERVAL: Duration = Duration::from_millis(200);
const ENGINE_STATE_EVENT: &str = "dbfox://engine-state";

impl Drop for EngineRuntime {
    fn drop(&mut self) {
        self.shutting_down.store(true, Ordering::Release);
        self.startup_cancelled.store(true, Ordering::Release);
        self.epoch.fetch_add(1, Ordering::AcqRel);
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
            shutting_down: AtomicBool::new(false),
            epoch: AtomicU64::new(0),
            next_generation: AtomicU64::new(0),
            restart_history: Mutex::new(VecDeque::new()),
            monitor_started: AtomicBool::new(false),
        }))
    }

    fn start_in_background(&self, log: SidecarLog, app: tauri::AppHandle) {
        let attempt_id = self.0.epoch.fetch_add(1, Ordering::AcqRel) + 1;
        let engine = self.clone();
        std::thread::spawn(move || {
            let progress_engine = engine.clone();
            let progress_app = app.clone();
            let mut started =
                EngineSupervisor::start(log, &engine.0.startup_cancelled, move |stage| {
                    if let Ok(mut current) = progress_engine.0.supervisor.lock() {
                        current.stage = Some(stage.to_string());
                    }
                    progress_engine.emit_status(&progress_app);
                });
            if engine.0.startup_cancelled.load(Ordering::Acquire)
                || engine.0.shutting_down.load(Ordering::Acquire)
                || engine.0.epoch.load(Ordering::Acquire) != attempt_id
            {
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
            if engine.0.startup_cancelled.load(Ordering::Acquire)
                || engine.0.shutting_down.load(Ordering::Acquire)
                || engine.0.epoch.load(Ordering::Acquire) != attempt_id
            {
                started.stop();
                return;
            }
            if started.state == EngineStartupState::Ready {
                started.generation = engine.0.next_generation.fetch_add(1, Ordering::AcqRel) + 1;
                started.restart_count = engine.restart_count();
            }
            *current = started;
            drop(current);
            engine.emit_status(&app);
        });
    }

    fn start_monitor(&self, log: SidecarLog, app: tauri::AppHandle) {
        if self
            .0
            .monitor_started
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .is_err()
        {
            return;
        }
        let engine = self.clone();
        std::thread::spawn(move || engine.monitor_loop(log, app));
    }

    fn monitor_loop(&self, log: SidecarLog, app: tauri::AppHandle) {
        while !self.0.shutting_down.load(Ordering::Acquire) {
            std::thread::sleep(ENGINE_EXIT_POLL_INTERVAL);
            let exit_message = {
                let mut current = match self.0.supervisor.lock() {
                    Ok(current) => current,
                    Err(_) => return,
                };
                match current.observe_unexpected_exit() {
                    Some(message) => message,
                    None => continue,
                }
            };

            log.event("error", "sidecar.unexpected_exit", &exit_message);
            let restart_count = self.record_restart();
            if let Ok(mut current) = self.0.supervisor.lock() {
                current.restart_count = restart_count as u32;
                if !restart_allowed(restart_count) {
                    current.state = EngineStartupState::Failed;
                    current.stage = Some("crash_loop".to_string());
                    current.error = Some(format!(
                        "Python engine exited more than {ENGINE_RESTART_LIMIT} times within {} seconds",
                        ENGINE_RESTART_WINDOW.as_secs()
                    ));
                }
            }
            self.emit_status(&app);
            if !restart_allowed(restart_count) {
                continue;
            }

            let observed_epoch = self.0.epoch.load(Ordering::Acquire);
            let backoff_ms = 500_u64.saturating_mul(1_u64 << (restart_count - 1).min(3));
            let deadline = Instant::now() + Duration::from_millis(backoff_ms);
            while Instant::now() < deadline {
                if self.0.shutting_down.load(Ordering::Acquire)
                    || self.0.epoch.load(Ordering::Acquire) != observed_epoch
                {
                    break;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            let should_restart = !self.0.shutting_down.load(Ordering::Acquire)
                && self.0.epoch.load(Ordering::Acquire) == observed_epoch
                && self
                    .0
                    .supervisor
                    .lock()
                    .map(|current| current.state == EngineStartupState::Restarting)
                    .unwrap_or(false);
            if should_restart {
                self.0.startup_cancelled.store(false, Ordering::Release);
                self.start_in_background(log.clone(), app.clone());
            }
        }
    }

    fn record_restart(&self) -> usize {
        let now = Instant::now();
        let mut history = match self.0.restart_history.lock() {
            Ok(history) => history,
            Err(_) => return ENGINE_RESTART_LIMIT + 1,
        };
        while history
            .front()
            .is_some_and(|instant| now.duration_since(*instant) > ENGINE_RESTART_WINDOW)
        {
            history.pop_front();
        }
        history.push_back(now);
        history.len()
    }

    fn restart_count(&self) -> u32 {
        self.0
            .restart_history
            .lock()
            .map(|history| history.len() as u32)
            .unwrap_or_default()
    }

    fn emit_status(&self, app: &tauri::AppHandle) {
        if let Ok(current) = self.0.supervisor.lock() {
            let _ = app.emit(ENGINE_STATE_EVENT, current.startup_status());
        }
    }

    fn restart(&self, log: SidecarLog, app: tauri::AppHandle) -> Result<(), String> {
        self.0.startup_cancelled.store(true, Ordering::Release);
        self.0.epoch.fetch_add(1, Ordering::AcqRel);
        {
            let mut current = self
                .0
                .supervisor
                .lock()
                .map_err(|_| "Engine supervisor lock poisoned".to_string())?;
            current.stop();
            *current = EngineSupervisor::starting();
        }
        if let Ok(mut history) = self.0.restart_history.lock() {
            history.clear();
        }
        self.0.shutting_down.store(false, Ordering::Release);
        self.0.startup_cancelled.store(false, Ordering::Release);
        self.start_in_background(log, app);
        Ok(())
    }

    fn stop(&self) {
        self.0.shutting_down.store(true, Ordering::Release);
        self.0.startup_cancelled.store(true, Ordering::Release);
        self.0.epoch.fetch_add(1, Ordering::AcqRel);
        if let Ok(mut current) = self.0.supervisor.lock() {
            current.stop();
        }
    }
}

fn restart_allowed(restart_count: usize) -> bool {
    restart_count <= ENGINE_RESTART_LIMIT
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct EngineConfig {
    port: u16,
    token: String,
    generation: u64,
    protocol_version: u16,
    server_info: EngineServerInfo,
    capabilities: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
struct EngineServerInfo {
    name: String,
    version: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum EngineStartupState {
    Starting,
    Restarting,
    Ready,
    Failed,
    Stopped,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct EngineStartupStatus {
    state: EngineStartupState,
    error: Option<String>,
    stage: Option<String>,
    generation: u64,
    restart_count: u32,
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
    engine.restart(sidecar_log, app)
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

#[tauri::command]
fn export_diagnostic_bundle(
    app: tauri::AppHandle,
    engine: tauri::State<'_, PythonEngine>,
    payload: DiagnosticBundlePayload,
) -> Result<DiagnosticBundleResult, String> {
    let log_directory = app
        .path()
        .app_log_dir()
        .map_err(|error| error.to_string())?;
    let status = engine
        .0
        .supervisor
        .lock()
        .map_err(|_| "Engine supervisor lock poisoned".to_string())?
        .startup_status();
    let host = HostDiagnosticSnapshot {
        app_version: env!("CARGO_PKG_VERSION").to_string(),
        os: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
        engine_state: format!("{:?}", status.state).to_ascii_lowercase(),
        engine_generation: status.generation,
        engine_restart_count: status.restart_count,
    };
    export_bundle(&log_directory, payload, host)
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
    stage: Option<String>,
    generation: u64,
    restart_count: u32,
    protocol_version: Option<u16>,
    server_info: Option<EngineServerInfo>,
    capabilities: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase")]
struct EngineReadyPayload {
    port: u16,
    protocol_version: u16,
    server_info: EngineServerInfo,
    capabilities: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct EngineStagePayload {
    stage: String,
}

impl EngineSupervisor {
    fn starting() -> Self {
        Self {
            child: None,
            port: None,
            token: String::new(),
            state: EngineStartupState::Starting,
            error: None,
            stage: Some("starting".to_string()),
            generation: 0,
            restart_count: 0,
            protocol_version: None,
            server_info: None,
            capabilities: Vec::new(),
        }
    }

    fn start<F>(log: SidecarLog, startup_cancelled: &AtomicBool, on_stage: F) -> Self
    where
        F: Fn(&str),
    {
        let token = generate_random_token();
        let mut supervisor = EngineSupervisor::starting();
        supervisor.token = token.clone();
        on_stage("launching");

        if startup_cancelled.load(Ordering::Acquire) {
            supervisor.stop();
            return supervisor;
        }

        let mut child = match spawn_python_engine(&token, &log) {
            Ok(child) => child,
            Err(error) => {
                supervisor.token.clear();
                supervisor.error = Some(error);
                supervisor.state = EngineStartupState::Failed;
                supervisor.stage = Some("failed".to_string());
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
                supervisor.token.clear();
                supervisor.error = Some(error);
                supervisor.state = EngineStartupState::Failed;
                supervisor.stage = Some("failed".to_string());
                return supervisor;
            }
        };

        let ready_lines = spawn_stdout_reader(stdout, log.clone());
        match wait_for_engine_ready(
            &mut child,
            &ready_lines,
            Duration::from_secs(20),
            startup_cancelled,
            &on_stage,
        )
        .and_then(|ready| {
            validate_engine_handshake(&ready)?;
            wait_for_engine_health(
                &mut child,
                ready.port,
                &token,
                &ready_lines,
                Duration::from_secs(20),
                startup_cancelled,
                &on_stage,
            )
            .map(|_| ready)
        }) {
            Ok(ready) => {
                if startup_cancelled.load(Ordering::Acquire) {
                    stop_engine_child(child);
                    supervisor.stop();
                } else {
                    log.info(
                        "sidecar.ready",
                        &format!("Python engine ready pid={} port={}", child.id(), ready.port),
                    );
                    supervisor.port = Some(ready.port);
                    supervisor.protocol_version = Some(ready.protocol_version);
                    supervisor.server_info = Some(ready.server_info);
                    supervisor.capabilities = ready.capabilities;
                    supervisor.state = EngineStartupState::Ready;
                    supervisor.stage = Some("ready".to_string());
                    supervisor.child = Some(child);
                }
            }
            Err(error) => {
                stop_engine_child(child);
                if startup_cancelled.load(Ordering::Acquire) {
                    supervisor.stop();
                } else {
                    log.error(&format!("Python engine failed readiness: {}", error));
                    supervisor.token.clear();
                    supervisor.error = Some(error);
                    supervisor.state = EngineStartupState::Failed;
                    supervisor.stage = Some("failed".to_string());
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
                    generation: self.generation,
                    protocol_version: self.protocol_version.ok_or_else(|| {
                        "Python engine did not provide a protocol version".to_string()
                    })?,
                    server_info: self.server_info.clone().ok_or_else(|| {
                        "Python engine did not provide server identity".to_string()
                    })?,
                    capabilities: self.capabilities.clone(),
                });
            }
        }
        match self.state {
            EngineStartupState::Starting => Err("Python engine is still starting".to_string()),
            EngineStartupState::Restarting => Err("Python engine is restarting".to_string()),
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
            stage: self.stage.clone(),
            generation: self.generation,
            restart_count: self.restart_count,
        }
    }

    fn observe_unexpected_exit(&mut self) -> Option<String> {
        if self.state != EngineStartupState::Ready {
            return None;
        }
        let status = self.child.as_mut()?.try_wait().ok()??;
        if let Some(mut child) = self.child.take() {
            let _ = child.wait();
        }
        self.port = None;
        self.token.clear();
        self.protocol_version = None;
        self.server_info = None;
        self.capabilities.clear();
        self.state = EngineStartupState::Restarting;
        self.stage = Some("restarting".to_string());
        let message = format!("Python engine exited unexpectedly: {status}");
        self.error = Some(message.clone());
        Some(message)
    }

    fn stop(&mut self) {
        if let Some(child) = self.child.take() {
            stop_engine_child(child);
        }
        self.port = None;
        self.token.clear();
        self.protocol_version = None;
        self.server_info = None;
        self.capabilities.clear();
        self.state = EngineStartupState::Stopped;
        self.error = None;
        self.stage = Some("stopped".to_string());
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default();

    // This must be the first plugin registered: the second process exits before
    // setup can create another sidecar or access the shared SQLite directory.
    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.unminimize();
            let _ = window.show();
            let _ = window.set_focus();
        }
    }));

    #[cfg(desktop)]
    let builder = builder.plugin(
        tauri_plugin_log::Builder::new()
            .targets([tauri_plugin_log::Target::new(
                tauri_plugin_log::TargetKind::LogDir {
                    file_name: Some("dbfox-host".to_string()),
                },
            )])
            .level(log::LevelFilter::Info)
            .max_file_size(2 * 1024 * 1024)
            .rotation_strategy(tauri_plugin_log::RotationStrategy::KeepSome(3))
            .format(|out, message, record| {
                let timestamp = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|duration| duration.as_secs())
                    .unwrap_or_default();
                let entry = serde_json::json!({
                    "timestampUnix": timestamp,
                    "level": record.level().to_string().to_ascii_lowercase(),
                    "target": record.target(),
                    "message": message.to_string(),
                });
                out.finish(format_args!("{entry}"));
            })
            .build(),
    );

    builder
        .setup(|app| {
            retire_legacy_temp_sidecar_log().map_err(std::io::Error::other)?;
            let log_directory = app
                .path()
                .app_log_dir()
                .map_err(|error| std::io::Error::other(error.to_string()))?;
            let sidecar_log = SidecarLog::new(log_directory).map_err(std::io::Error::other)?;
            let engine = PythonEngine::starting();
            app.manage(engine.clone());
            engine.start_in_background(sidecar_log.clone(), app.handle().clone());
            engine.start_monitor(sidecar_log, app.handle().clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_engine_config,
            get_engine_startup_status,
            restart_python_engine,
            open_diagnostic_logs,
            export_diagnostic_bundle
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
    engine.stop();
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

/// Use Cargo's authoritative build target rather than reconstructing it from OS/arch.
fn current_target_triplet() -> &'static str {
    env!("DBFOX_TARGET_TRIPLE")
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

fn parse_engine_ready_line(line: &str) -> Option<EngineReadyPayload> {
    let payload = line.strip_prefix("DBFOX_ENGINE_READY")?.trim();
    serde_json::from_str::<EngineReadyPayload>(payload).ok()
}

fn validate_engine_handshake(ready: &EngineReadyPayload) -> Result<(), String> {
    if ready.protocol_version != ENGINE_PROTOCOL_VERSION {
        return Err(format!(
            "Incompatible Python engine protocol: expected {ENGINE_PROTOCOL_VERSION}, received {}",
            ready.protocol_version
        ));
    }
    if ready.server_info.name != "dbfox-engine" || ready.server_info.version.trim().is_empty() {
        return Err("Python engine reported an invalid server identity".to_string());
    }
    for capability in ["http", "sse", "problem-details"] {
        if !ready.capabilities.iter().any(|value| value == capability) {
            return Err(format!(
                "Python engine is missing required capability: {capability}"
            ));
        }
    }
    Ok(())
}

fn parse_engine_stage_line(line: &str) -> Option<String> {
    let payload = line.strip_prefix("DBFOX_ENGINE_STAGE")?.trim();
    serde_json::from_str::<EngineStagePayload>(payload)
        .ok()
        .map(|value| value.stage)
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

fn wait_for_engine_ready<F>(
    child: &mut Child,
    lines: &mpsc::Receiver<String>,
    timeout: Duration,
    startup_cancelled: &AtomicBool,
    on_stage: &F,
) -> Result<EngineReadyPayload, String>
where
    F: Fn(&str),
{
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if startup_cancelled.load(Ordering::Acquire) {
            return Err("Python engine startup was cancelled".to_string());
        }
        match lines.recv_timeout(Duration::from_millis(100)) {
            Ok(line) => {
                if let Some(ready) = parse_engine_ready_line(&line) {
                    on_stage("initializing");
                    return Ok(ready);
                }
                if let Some(stage) = parse_engine_stage_line(&line) {
                    on_stage(&stage);
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

fn wait_for_engine_health<F>(
    child: &mut Child,
    port: u16,
    token: &str,
    lines: &mpsc::Receiver<String>,
    timeout: Duration,
    startup_cancelled: &AtomicBool,
    on_stage: &F,
) -> Result<(), String>
where
    F: Fn(&str),
{
    let deadline = Instant::now() + timeout;
    let mut last_error = "health endpoint was not reachable".to_string();
    while Instant::now() < deadline {
        if startup_cancelled.load(Ordering::Acquire) {
            return Err("Python engine startup was cancelled".to_string());
        }
        while let Ok(line) = lines.try_recv() {
            if let Some(stage) = parse_engine_stage_line(&line) {
                on_stage(&stage);
            }
        }
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!(
                "Python engine exited before becoming healthy: {} ({})",
                status, last_error
            ));
        }
        match probe_engine_health(port, token) {
            Ok(()) => return Ok(()),
            Err(error) => last_error = error,
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    Err(format!(
        "Timed out waiting for Python engine health endpoint: {}",
        last_error
    ))
}

fn probe_engine_health(port: u16, token: &str) -> Result<(), String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(500))
        .map_err(|error| format!("connect failed: {}", error))?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    let request = format!(
        "GET /api/v1/health HTTP/1.1\r\nHost: 127.0.0.1\r\nOrigin: tauri://localhost\r\nX-Local-Token: {token}\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
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

        let mut command = Command::new(&final_path);
        command
            .env("DBFOX_ENGINE_PORT", "0")
            .env("DBFOX_ENGINE_TOKEN", token)
            .current_dir(exe_dir)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(target_os = "windows")]
        command.creation_flags(CREATE_NO_WINDOW);

        match command.spawn() {
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
        let line = r#"DBFOX_ENGINE_READY {"port":18731,"protocolVersion":1,"serverInfo":{"name":"dbfox-engine","version":"1.0.3"},"capabilities":["http","sse","problem-details"]}"#;

        let ready = parse_engine_ready_line(line).expect("ready payload");
        assert_eq!(ready.port, 18731);
        assert_eq!(ready.protocol_version, 1);
        assert_eq!(ready.server_info.name, "dbfox-engine");
        assert!(validate_engine_handshake(&ready).is_ok());
        assert!(parse_engine_ready_line(r#"DBFOX_ENGINE_READY {"port":18731}"#).is_none());
    }

    #[test]
    fn ignores_non_ready_stdout_line() {
        assert_eq!(
            parse_engine_ready_line("INFO: started server process"),
            None
        );
    }

    #[test]
    fn parses_engine_stage_stdout_line() {
        let line = r#"DBFOX_ENGINE_STAGE {"stage":"migrating"}"#;
        assert_eq!(parse_engine_stage_line(line), Some("migrating".to_string()));
        assert_eq!(parse_engine_stage_line("INFO: migration started"), None);
    }

    #[test]
    fn engine_health_wait_has_a_total_deadline() {
        let mut child = Command::new("ping")
            .args(["127.0.0.1", "-n", "6"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("test child should start");
        let (_sender, receiver) = mpsc::channel();
        let cancelled = AtomicBool::new(false);

        let result = wait_for_engine_health(
            &mut child,
            1,
            "health-probe-test-token",
            &receiver,
            Duration::from_millis(1),
            &cancelled,
            &|_| {},
        );
        stop_engine_child(child);

        assert!(result
            .expect_err("health wait must time out")
            .contains("Timed out waiting for Python engine health endpoint"));
    }

    #[test]
    fn engine_health_probe_sends_the_runtime_token_and_tauri_origin() {
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0))
            .expect("health test listener should bind");
        let port = listener.local_addr().expect("listener address").port();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("health probe connection");
            let mut buffer = [0_u8; 2048];
            let size = stream.read(&mut buffer).expect("health request");
            stream
                .write_all(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 20\r\nConnection: close\r\n\r\n{\"status\":\"healthy\"}",
                )
                .expect("health response");
            String::from_utf8_lossy(&buffer[..size]).into_owned()
        });

        probe_engine_health(port, "current-runtime-token").expect("health probe should pass");
        let request = server.join().expect("health server should finish");

        assert!(request.contains("X-Local-Token: current-runtime-token\r\n"));
        assert!(request.contains("Origin: tauri://localhost\r\n"));
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
            stage: Some("ready".to_string()),
            generation: 7,
            restart_count: 0,
            protocol_version: Some(ENGINE_PROTOCOL_VERSION),
            server_info: Some(EngineServerInfo {
                name: "dbfox-engine".to_string(),
                version: "1.0.3".to_string(),
            }),
            capabilities: vec![
                "http".to_string(),
                "sse".to_string(),
                "problem-details".to_string(),
            ],
        };

        let config = supervisor
            .engine_config()
            .expect("ready supervisor should expose config");
        assert_eq!(config.port, 18731);
        assert_eq!(config.token, "test-token");
        assert_eq!(config.generation, 7);
        assert_eq!(config.protocol_version, ENGINE_PROTOCOL_VERSION);
    }

    #[test]
    fn supervisor_invalidates_config_when_ready_child_exits() {
        #[cfg(target_os = "windows")]
        let child = Command::new("cmd")
            .args(["/C", "exit", "7"])
            .spawn()
            .expect("test child should start");
        #[cfg(not(target_os = "windows"))]
        let child = Command::new("sh")
            .args(["-c", "exit 7"])
            .spawn()
            .expect("test child should start");

        let mut supervisor = EngineSupervisor {
            child: Some(child),
            port: Some(18731),
            token: "test-token".to_string(),
            state: EngineStartupState::Ready,
            error: None,
            stage: Some("ready".to_string()),
            generation: 3,
            restart_count: 0,
            protocol_version: Some(ENGINE_PROTOCOL_VERSION),
            server_info: Some(EngineServerInfo {
                name: "dbfox-engine".to_string(),
                version: "1.0.3".to_string(),
            }),
            capabilities: vec![
                "http".to_string(),
                "sse".to_string(),
                "problem-details".to_string(),
            ],
        };
        let deadline = Instant::now() + Duration::from_secs(2);
        let message = loop {
            if let Some(message) = supervisor.observe_unexpected_exit() {
                break message;
            }
            assert!(Instant::now() < deadline, "test child did not exit in time");
            std::thread::sleep(Duration::from_millis(10));
        };

        assert!(message.contains("exited unexpectedly"));
        assert_eq!(supervisor.state, EngineStartupState::Restarting);
        assert!(supervisor.port.is_none());
        assert!(supervisor.token.is_empty());
        assert!(supervisor.engine_config().is_err());
    }

    #[test]
    fn crash_loop_policy_allows_three_restarts_then_stops() {
        assert!(restart_allowed(1));
        assert!(restart_allowed(2));
        assert!(restart_allowed(3));
        assert!(!restart_allowed(4));
    }

    #[test]
    fn shutdown_prevents_exit_watcher_from_reclassifying_the_engine() {
        let mut supervisor = EngineSupervisor::starting();
        supervisor.stop();

        assert_eq!(supervisor.state, EngineStartupState::Stopped);
        assert!(supervisor.observe_unexpected_exit().is_none());
        assert_eq!(supervisor.state, EngineStartupState::Stopped);
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
