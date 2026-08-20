use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager};
use tauri_plugin_opener::OpenerExt;

mod app_updates;
mod crash_recovery;
mod diagnostic_bundle;
mod dlc_asset_protocol;
mod external_image;
mod project_folder;
mod sidecar_log;
mod sidecar_process;

use app_updates::{
    check_for_app_update, get_update_configuration, install_pending_app_update, PendingUpdate,
};
use crash_recovery::{get_launch_recovery_status, CrashRecoveryState};
use diagnostic_bundle::{
    export_bundle, DiagnosticBundlePayload, DiagnosticBundleResult, HostDiagnosticSnapshot,
};
use dlc_asset_protocol::{
    handle_dlc_asset_request, DlcAssetHostState, RuntimeDlcActivationProjection,
};
use external_image::save_external_image;
use project_folder::{list_project_folder, pick_project_folder, read_project_file};
use sidecar_log::{retire_legacy_temp_sidecar_log, SidecarLog, SIDECAR_LOG_TARGET};
use sidecar_process::{spawn_python_engine, EngineChild};

// build_sidecar.py and the Tauri external-bin contract intentionally publish
// Windows artifacts with the MSVC triplet.  Reject a GNU host explicitly
// instead of producing an installer whose Rust binary and sidecar disagree.
#[cfg(all(target_os = "windows", target_env = "gnu"))]
compile_error!(
    "DBFox Windows desktop builds require the MSVC Rust toolchain (for example: cargo +stable-x86_64-pc-windows-msvc ...)."
);

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
    dlc_asset_state: DlcAssetHostState,
}

const ENGINE_PROTOCOL_VERSION: u16 = 1;
const ENGINE_RESTART_LIMIT: usize = 3;
const ENGINE_RESTART_WINDOW: Duration = Duration::from_secs(60);
const ENGINE_EXIT_POLL_INTERVAL: Duration = Duration::from_millis(200);
const ENGINE_STATE_EVENT: &str = "dbfox://engine-state";
const MAX_ENGINE_HEALTH_RESPONSE_BYTES: usize = 64 * 1024;

impl Drop for EngineRuntime {
    fn drop(&mut self) {
        self.shutting_down.store(true, Ordering::Release);
        self.startup_cancelled.store(true, Ordering::Release);
        self.epoch.fetch_add(1, Ordering::AcqRel);
        self.dlc_asset_state.clear();
        if let Ok(supervisor) = self.supervisor.get_mut() {
            supervisor.stop();
        }
    }
}

impl PythonEngine {
    fn starting(dlc_asset_state: DlcAssetHostState) -> Self {
        Self(Arc::new(EngineRuntime {
            supervisor: Mutex::new(EngineSupervisor::starting()),
            startup_cancelled: AtomicBool::new(false),
            shutting_down: AtomicBool::new(false),
            epoch: AtomicU64::new(0),
            next_generation: AtomicU64::new(0),
            restart_history: Mutex::new(VecDeque::new()),
            monitor_started: AtomicBool::new(false),
            dlc_asset_state,
        }))
    }

    fn start_in_background(&self, log: SidecarLog, app: tauri::AppHandle) {
        let attempt_id = self.0.epoch.fetch_add(1, Ordering::AcqRel) + 1;
        let engine = self.clone();
        std::thread::spawn(move || {
            let progress_engine = engine.clone();
            let callback_app = app.clone();
            let mut started =
                EngineSupervisor::start(&app, log, &engine.0.startup_cancelled, move |stage| {
                    if let Ok(mut current) = progress_engine.0.supervisor.lock() {
                        current.stage = Some(stage.to_string());
                    }
                    progress_engine.emit_status(&callback_app);
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
                if let (Some(port), token) = (started.port, &started.token) {
                    if let Ok(projection) = fetch_dlc_activation_projection(port, token) {
                        engine.0.dlc_asset_state.update_projection(projection);
                    }
                }
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

            log.event(log::Level::Error, "sidecar.unexpected_exit", &exit_message);
            self.0.dlc_asset_state.clear();
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
                self.start_in_background(log, app.clone());
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
        self.0.dlc_asset_state.clear();
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
    engine.restart(SidecarLog, app)
}

#[tauri::command]
fn open_diagnostic_logs(app: tauri::AppHandle) -> Result<(), String> {
    let log_directory = app
        .path()
        .app_log_dir()
        .map_err(|error| error.to_string())?;
    std::fs::create_dir_all(&log_directory).map_err(|error| error.to_string())?;
    let log_directory = log_directory
        .to_str()
        .ok_or_else(|| "Diagnostic log directory is not valid Unicode".to_string())?;
    app.opener()
        .open_path(log_directory, None::<&str>)
        .map_err(|error| format!("Failed to open diagnostic log directory: {error}"))
}

fn validate_external_https_url(raw_url: &str) -> Result<tauri::Url, String> {
    if raw_url.is_empty() || raw_url.trim() != raw_url {
        return Err("External URL must not be empty or contain surrounding whitespace".to_string());
    }
    let url = tauri::Url::parse(raw_url).map_err(|_| "External URL is invalid".to_string())?;
    if url.scheme() != "https"
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err("Only absolute HTTPS URLs without credentials may be opened".to_string());
    }
    Ok(url)
}

#[tauri::command]
fn open_external_https_url(app: tauri::AppHandle, url: String) -> Result<(), String> {
    let url = validate_external_https_url(&url)?;
    app.opener()
        .open_url(url.as_str(), None::<&str>)
        .map_err(|error| format!("Failed to open external HTTPS URL: {error}"))
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
    child: Option<EngineChild>,
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

    fn start<F>(
        app: &tauri::AppHandle,
        log: SidecarLog,
        startup_cancelled: &AtomicBool,
        on_stage: F,
    ) -> Self
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

        let (mut child, ready_lines) = match spawn_python_engine(app, &token, &log) {
            Ok(spawned) => spawned,
            Err(error) => {
                supervisor.token.clear();
                supervisor.error = Some(error);
                supervisor.state = EngineStartupState::Failed;
                supervisor.stage = Some("failed".to_string());
                return supervisor;
            }
        };

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
                    child.stop();
                    supervisor.stop();
                } else {
                    log.info(
                        "sidecar.ready",
                        &format!(
                            "Python engine ready pid={} port={}",
                            child.pid(),
                            ready.port
                        ),
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
                child.stop();
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
        let observation = self.child.as_mut()?.try_wait();
        let message = match observation {
            Ok(Some(status)) => format!("Python engine exited unexpectedly: {status}"),
            Ok(None) => return None,
            Err(error) => {
                if let Some(child) = self.child.take() {
                    child.stop();
                }
                format!("Python engine exit monitoring failed: {error}")
            }
        };
        self.child.take();
        self.port = None;
        self.token.clear();
        self.protocol_version = None;
        self.server_info = None;
        self.capabilities.clear();
        self.state = EngineStartupState::Restarting;
        self.stage = Some("restarting".to_string());
        self.error = Some(message.clone());
        Some(message)
    }

    fn stop(&mut self) {
        if let Some(child) = self.child.take() {
            child.stop();
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

    // Restore native geometry through Tauri's official plugin. The configured
    // window starts hidden so the restored bounds are applied before first paint.
    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_window_state::Builder::default().build());

    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_updater::Builder::new().build());

    #[cfg(desktop)]
    let builder = builder.plugin(
        tauri_plugin_log::Builder::new()
            // The builder formatter runs before target formatters. Keep the
            // shared dispatch transparent so the Sidecar target can persist
            // DBFox's already-structured event without wrapping it in a
            // second JSON envelope.
            .clear_format()
            .targets([
                tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::LogDir {
                    file_name: Some("dbfox-host".to_string()),
                })
                .filter(|metadata| metadata.target() != SIDECAR_LOG_TARGET)
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
                }),
                tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::LogDir {
                    file_name: Some("dbfox-sidecar".to_string()),
                })
                .filter(|metadata| metadata.target() == SIDECAR_LOG_TARGET)
                .format(|out, message, _record| out.finish(format_args!("{message}"))),
            ])
            .level(log::LevelFilter::Info)
            .max_file_size(2 * 1024 * 1024)
            .rotation_strategy(tauri_plugin_log::RotationStrategy::KeepSome(3))
            .build(),
    );

    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_shell::init());

    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_opener::init());

    #[cfg(desktop)]
    let builder = builder.plugin(tauri_plugin_dialog::init());

    let dlc_asset_state = DlcAssetHostState::new();
    let dlc_asset_protocol_state = dlc_asset_state.clone();

    let builder = builder.register_asynchronous_uri_scheme_protocol(
        "dlc-asset",
        move |_app, request, responder| {
            let response = handle_dlc_asset_request(&dlc_asset_protocol_state, request);
            responder.respond(response);
        },
    );

    builder
        .setup(move |app| {
            retire_legacy_temp_sidecar_log().map_err(std::io::Error::other)?;
            let recovery = CrashRecoveryState::initialize(app.handle())?;
            app.manage(recovery);
            app.manage(PendingUpdate::default());
            app.manage(dlc_asset_state.clone());
            let sidecar_log = SidecarLog;
            let engine = PythonEngine::starting(dlc_asset_state);
            app.manage(engine.clone());
            engine.start_in_background(sidecar_log, app.handle().clone());
            engine.start_monitor(sidecar_log, app.handle().clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_engine_config,
            get_engine_startup_status,
            restart_python_engine,
            open_diagnostic_logs,
            open_external_https_url,
            save_external_image,
            pick_project_folder,
            list_project_folder,
            read_project_file,
            export_diagnostic_bundle,
            get_launch_recovery_status,
            get_update_configuration,
            check_for_app_update,
            install_pending_app_update
        ])
        .on_window_event(|window, event| {
            if matches!(
                event,
                tauri::WindowEvent::CloseRequested { .. } | tauri::WindowEvent::Destroyed
            ) {
                if let Some(engine) = window.try_state::<PythonEngine>() {
                    stop_python_engine(&engine);
                }
                if let Some(recovery) = window.try_state::<CrashRecoveryState>() {
                    recovery.clear();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running DBFox");
}
fn stop_python_engine(engine: &PythonEngine) {
    engine.stop();
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

fn wait_for_engine_ready<F>(
    child: &mut EngineChild,
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
    child: &mut EngineChild,
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
    let mut response = Vec::new();
    stream
        .take((MAX_ENGINE_HEALTH_RESPONSE_BYTES + 1) as u64)
        .read_to_end(&mut response)
        .map_err(|error| format!("health response read failed: {}", error))?;
    if response.len() > MAX_ENGINE_HEALTH_RESPONSE_BYTES {
        return Err("health response exceeded the maximum allowed size".to_string());
    }

    validate_engine_health_response(&response)
}

#[derive(Debug, Deserialize)]
struct EngineHealthResponse {
    status: String,
}

fn validate_engine_health_response(response: &[u8]) -> Result<(), String> {
    let header_end = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| "health response did not contain complete HTTP headers".to_string())?;
    let headers = std::str::from_utf8(&response[..header_end])
        .map_err(|_| "health response headers were not valid UTF-8".to_string())?;
    let mut status_parts = headers
        .lines()
        .next()
        .ok_or_else(|| "health response did not contain an HTTP status line".to_string())?
        .split_ascii_whitespace();
    let protocol = status_parts.next().unwrap_or_default();
    let status_code = status_parts.next().unwrap_or_default();
    if !matches!(protocol, "HTTP/1.0" | "HTTP/1.1") || status_code != "200" {
        return Err("health endpoint did not return HTTP 200".to_string());
    }

    let body = &response[(header_end + 4)..];
    let health: EngineHealthResponse = serde_json::from_slice(body)
        .map_err(|_| "health endpoint did not return the expected JSON contract".to_string())?;
    if health.status != "healthy" {
        return Err("health endpoint did not return healthy status".to_string());
    }
    Ok(())
}

fn fetch_dlc_activation_projection(
    port: u16,
    token: &str,
) -> Result<RuntimeDlcActivationProjection, String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(1000))
        .map_err(|error| format!("connect failed: {}", error))?;
    let _ = stream.set_read_timeout(Some(Duration::from_millis(2000)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(1000)));
    let request = format!(
        "GET /api/v1/dlcs/activation HTTP/1.1\r\nHost: 127.0.0.1\r\nOrigin: tauri://localhost\r\nX-Local-Token: {token}\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|error| format!("activation request write failed: {}", error))?;
    let mut response = Vec::new();
    stream
        .take(MAX_ENGINE_HEALTH_RESPONSE_BYTES as u64)
        .read_to_end(&mut response)
        .map_err(|error| format!("activation response read failed: {}", error))?;

    let header_end = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| "activation response did not contain complete HTTP headers".to_string())?;
    let headers = std::str::from_utf8(&response[..header_end])
        .map_err(|_| "activation response headers were not valid UTF-8".to_string())?;
    let mut status_parts = headers
        .lines()
        .next()
        .ok_or_else(|| "activation response did not contain an HTTP status line".to_string())?
        .split_ascii_whitespace();
    let protocol = status_parts.next().unwrap_or_default();
    let status_code = status_parts.next().unwrap_or_default();
    if !matches!(protocol, "HTTP/1.0" | "HTTP/1.1") || status_code != "200" {
        return Err(format!("activation endpoint returned HTTP {status_code}"));
    }

    let body = &response[(header_end + 4)..];
    serde_json::from_slice(body)
        .map_err(|error| format!("failed to parse activation projection JSON: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

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
        let (mut child, _termination_sender) = EngineChild::test_running();
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
        child.stop();

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
    fn engine_health_response_rejects_a_healthy_word_outside_the_status_field() {
        let response = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"message\":\"healthy\",\"status\":\"failed\"}";

        assert!(validate_engine_health_response(response)
            .expect_err("failed status must not be accepted")
            .contains("did not return healthy status"));
    }

    #[test]
    fn engine_health_response_rejects_malformed_or_non_success_responses() {
        for response in [
            b"HTTP/1.1 503 Service Unavailable\r\n\r\n{\"status\":\"healthy\"}".as_slice(),
            b"HTTP/1.1 200 OK\r\n\r\n{\"status\":true}".as_slice(),
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json".as_slice(),
        ] {
            assert!(validate_engine_health_response(response).is_err());
        }
    }

    #[test]
    fn external_navigation_accepts_only_absolute_https_without_credentials() {
        assert_eq!(
            validate_external_https_url("https://cdn.example.com/image.png?width=640")
                .expect("safe HTTPS URL")
                .as_str(),
            "https://cdn.example.com/image.png?width=640"
        );
        for rejected in [
            "http://cdn.example.com/image.png",
            "https://alice:secret@cdn.example.com/image.png",
            "file:///C:/private.png",
            " https://cdn.example.com/image.png",
            "not-a-url",
        ] {
            assert!(validate_external_https_url(rejected).is_err(), "{rejected}");
        }
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
        let child = EngineChild::test_exited(7);

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
    fn exit_channel_failure_is_observable_and_invalidates_ready_config() {
        let (child, sender) = EngineChild::test_running();
        let mut supervisor = EngineSupervisor {
            child: Some(child),
            port: Some(18731),
            token: "test-token".to_string(),
            state: EngineStartupState::Ready,
            error: None,
            stage: Some("ready".to_string()),
            generation: 1,
            restart_count: 0,
            protocol_version: Some(ENGINE_PROTOCOL_VERSION),
            server_info: None,
            capabilities: vec![],
        };
        sender
            .send(Err("event channel disconnected".to_string()))
            .expect("test channel should accept terminal error");

        let message = supervisor
            .observe_unexpected_exit()
            .expect("monitor failure must be observable");

        assert!(message.contains("exit monitoring failed"));
        assert_eq!(supervisor.state, EngineStartupState::Restarting);
        assert!(supervisor.engine_config().is_err());
        assert!(supervisor.token.is_empty());
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
}
