use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::sync::mpsc;
use std::time::{Duration, Instant};
use tauri::Manager;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct PythonEngine(Mutex<EngineSupervisor>);

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EngineConfig {
    port: u16,
    token: String,
}

#[tauri::command]
fn get_engine_config(engine: tauri::State<'_, PythonEngine>) -> Result<EngineConfig, String> {
    let guard = engine.0.lock().map_err(|_| "Engine supervisor lock poisoned".to_string())?;
    guard.engine_config()
}

fn generate_random_token() -> String {
    use rand::RngCore;
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}
impl Drop for PythonEngine {
    fn drop(&mut self) {
        stop_python_engine(self);
    }
}

#[derive(Debug)]
struct EngineSupervisor {
    child: Option<Child>,
    port: Option<u16>,
    token: String,
    ready: bool,
    error: Option<String>,
}

#[derive(Debug, Deserialize)]
struct EngineReadyPayload {
    port: u16,
}

impl EngineSupervisor {
    fn start() -> Self {
        let token = generate_random_token();
        let mut supervisor = EngineSupervisor {
            child: None,
            port: None,
            token: token.clone(),
            ready: false,
            error: None,
        };

        let mut child = match spawn_python_engine(&token) {
            Ok(child) => child,
            Err(error) => {
                supervisor.error = Some(error);
                return supervisor;
            }
        };

        if let Some(stderr) = child.stderr.take() {
            drain_engine_pipe(stderr, "stderr");
        }

        let stdout = match child.stdout.take() {
            Some(stdout) => stdout,
            None => {
                let error = "Python engine stdout was not captured".to_string();
                log_sidecar_error(&error);
                stop_engine_child(child);
                supervisor.error = Some(error);
                return supervisor;
            }
        };

        let ready_lines = spawn_stdout_reader(stdout);
        match wait_for_engine_ready(&mut child, ready_lines, Duration::from_secs(20))
            .and_then(|port| wait_for_engine_health(port, Duration::from_secs(20)).map(|_| port))
        {
            Ok(port) => {
                supervisor.port = Some(port);
                supervisor.ready = true;
                supervisor.child = Some(child);
            }
            Err(error) => {
                log_sidecar_error(&format!("Python engine failed readiness: {}", error));
                stop_engine_child(child);
                supervisor.error = Some(error);
            }
        }

        supervisor
    }

    fn engine_config(&self) -> Result<EngineConfig, String> {
        if self.ready {
            if let Some(port) = self.port {
                return Ok(EngineConfig {
                    port,
                    token: self.token.clone(),
                });
            }
        }
        Err(self
            .error
            .clone()
            .unwrap_or_else(|| "Python engine is not ready".to_string()))
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let engine_supervisor = EngineSupervisor::start();

    tauri::Builder::default()
        .manage(PythonEngine(Mutex::new(engine_supervisor)))
        .invoke_handler(tauri::generate_handler![get_engine_config])
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
fn log_sidecar_error(message: &str) {
    let log_path = std::env::temp_dir().join("dbfox-sidecar.log");
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs().to_string())
        .unwrap_or_default();
    let entry = format!("[{}] {}\n", ts, message);
    let _ = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .and_then(|mut f| std::io::Write::write_all(&mut f, entry.as_bytes()));
    eprintln!("{}", message);
}

fn stop_python_engine(engine: &PythonEngine) {
    if let Ok(mut guard) = engine.0.lock() {
        if let Some(child) = guard.child.take() {
            stop_engine_child(child);
        }
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
        vec![
            "dbfox-engine".into(),
            format!("dbfox-engine-{}", triplet),
        ]
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

fn spawn_stdout_reader<R>(stdout: R) -> mpsc::Receiver<String>
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
                    log_sidecar_error(&format!("Failed reading Python engine stdout: {}", error));
                    break;
                }
            }
        }
    });
    rx
}

fn drain_engine_pipe<R>(pipe: R, stream_name: &'static str)
where
    R: Read + Send + 'static,
{
    std::thread::spawn(move || {
        let reader = BufReader::new(pipe);
        for line in reader.lines().flatten() {
            log_sidecar_error(&format!("Python engine {}: {}", stream_name, line));
        }
    });
}

fn wait_for_engine_ready(
    child: &mut Child,
    lines: mpsc::Receiver<String>,
    timeout: Duration,
) -> Result<u16, String> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
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

fn wait_for_engine_health(port: u16, timeout: Duration) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    let mut last_error = "health endpoint was not reachable".to_string();
    while Instant::now() < deadline {
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

fn spawn_python_engine(token: &str) -> Result<Child, String> {
    if cfg!(debug_assertions) {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .to_path_buf();
        match Command::new("python")
            .args(["-m", "engine.main"])
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
                log_sidecar_error(&error);
                Err(error)
            }
        }
    } else {
        // Production Mode: Spawn the sidecar binary directly
        let exe_path = match std::env::current_exe() {
            Ok(path) => path,
            Err(e) => {
                let error = format!("Unable to resolve current exe path: {}", e);
                log_sidecar_error(&error);
                return Err(error);
            }
        };
        let exe_dir = match exe_path.parent() {
            Some(dir) => dir,
            None => {
                let error = "Unable to resolve exe parent directory".to_string();
                log_sidecar_error(&error);
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
                let error = format!(
                    "Failed to start Sidecar Engine at {:?}: {}",
                    final_path, e
                );
                log_sidecar_error(&error);
                Err(error)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
        assert_eq!(parse_engine_ready_line("INFO: started server process"), None);
    }

    #[test]
    fn supervisor_returns_config_only_when_ready() {
        let supervisor = EngineSupervisor {
            child: None,
            port: Some(18731),
            token: "test-token".to_string(),
            ready: true,
            error: None,
        };

        let config = supervisor.engine_config().expect("ready supervisor should expose config");
        assert_eq!(config.port, 18731);
        assert_eq!(config.token, "test-token");
    }
}
