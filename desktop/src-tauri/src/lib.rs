use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct PythonEngine(Mutex<Option<Child>>);

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EngineConfig {
    port: u16,
    token: String,
}

#[tauri::command]
fn get_engine_config(config: tauri::State<'_, EngineConfig>) -> EngineConfig {
    config.inner().clone()
}

fn get_free_port() -> Option<u16> {
    std::net::TcpListener::bind("127.0.0.1:0")
        .and_then(|listener| listener.local_addr())
        .map(|addr| addr.port())
        .ok()
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port = get_free_port().unwrap_or(18625);
    let token = generate_random_token();
    let python_child = spawn_python_engine(port, &token);

    tauri::Builder::default()
        .manage(EngineConfig { port, token })
        .manage(PythonEngine(Mutex::new(python_child)))
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
    let _ = std::fs::write(&log_path, entry);
    eprintln!("{}", message);
}

fn stop_python_engine(engine: &PythonEngine) {
    if let Ok(mut guard) = engine.0.lock() {
        if let Some(child) = guard.take() {
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

fn spawn_python_engine(port: u16, token: &str) -> Option<Child> {
    if cfg!(debug_assertions) {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .to_path_buf();
        let engine_path = root.join("engine").join("main.py");

        match Command::new("python")
            .arg(&engine_path)
            .env("PYTHONPATH", &root)
            .env("DBFOX_ENGINE_PORT", port.to_string())
            .env("DBFOX_ENGINE_TOKEN", token)
            .current_dir(&root)
            .spawn()
        {
            Ok(child) => {
                println!("DBFox Python Engine (Dev) started (pid: {})", child.id());
                Some(child)
            }
            Err(e) => {
                log_sidecar_error(&format!("Failed to start Python Dev engine: {}", e));
                None
            }
        }
    } else {
        // Production Mode: Spawn the sidecar binary directly
        let exe_path = match std::env::current_exe() {
            Ok(path) => path,
            Err(e) => {
                log_sidecar_error(&format!("Unable to resolve current exe path: {}", e));
                return None;
            }
        };
        let exe_dir = match exe_path.parent() {
            Some(dir) => dir,
            None => {
                log_sidecar_error("Unable to resolve exe parent directory");
                return None;
            }
        };

        let candidates = sidecar_candidate_paths(exe_dir);
        let sidecar_path = candidates.iter().find(|path| path.exists()).cloned();

        let final_path = sidecar_path.unwrap_or_else(|| candidates[0].clone());

        match Command::new(&final_path)
            .env("DBFOX_ENGINE_PORT", port.to_string())
            .env("DBFOX_ENGINE_TOKEN", token)
            .current_dir(exe_dir)
            .spawn()
        {
            Ok(child) => {
                println!("DBFox Sidecar Engine (Prod) started (pid: {})", child.id());
                Some(child)
            }
            Err(e) => {
                log_sidecar_error(&format!(
                    "Failed to start Sidecar Engine at {:?}: {}",
                    final_path, e
                ));
                None
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
}
