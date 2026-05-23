use std::process::{Child, Command};
use std::sync::Mutex;

struct PythonEngine(Mutex<Option<Child>>);

impl Drop for PythonEngine {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(ref mut child) = *guard {
                let _ = child.kill();
            }
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let python_child = spawn_python_engine();

    tauri::Builder::default()
        .manage(PythonEngine(Mutex::new(python_child)))
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let _ = window;
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running DataBox");
}

fn spawn_python_engine() -> Option<Child> {
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
            .current_dir(&root)
            .spawn()
        {
            Ok(child) => {
                println!("DataBox Python Engine (Dev) started (pid: {})", child.id());
                Some(child)
            }
            Err(e) => {
                eprintln!("Warning: Failed to start Python Dev engine: {}", e);
                None
            }
        }
    } else {
        // Production Mode: Spawn the sidecar binary directly
        let exe_path = match std::env::current_exe() {
            Ok(path) => path,
            Err(e) => {
                eprintln!("Error: Unable to resolve current exe path: {}", e);
                return None;
            }
        };
        let exe_dir = match exe_path.parent() {
            Some(dir) => dir,
            None => {
                eprintln!("Error: Unable to resolve exe parent directory");
                return None;
            }
        };
        
        // Resolve target triplet name
        let sidecar_name = if cfg!(target_os = "windows") {
            "databox-engine-x86_64-pc-windows-msvc.exe".to_string()
        } else if cfg!(target_os = "macos") {
            "databox-engine-x86_64-apple-darwin".to_string()
        } else {
            "databox-engine-x86_64-unknown-linux-gnu".to_string()
        };

        // Tauri packages sidecars next to the executable, inside "_up_", or "resources"
        let candidates = [
            exe_dir.join(&sidecar_name),
            exe_dir.join("_up_").join("binaries").join(&sidecar_name),
            exe_dir.join("resources").join("binaries").join(&sidecar_name),
            exe_dir.join("binaries").join(&sidecar_name),
        ];

        let mut sidecar_path = None;
        for path in &candidates {
            if path.exists() {
                sidecar_path = Some(path.clone());
                break;
            }
        }

        // Fallback if none exist yet (helps during tauri build packaging phase)
        let final_path = sidecar_path.unwrap_or_else(|| exe_dir.join(&sidecar_name));

        match Command::new(&final_path)
            .current_dir(exe_dir)
            .spawn()
        {
            Ok(child) => {
                println!("DataBox Sidecar Engine (Prod) started (pid: {})", child.id());
                Some(child)
            }
            Err(e) => {
                eprintln!("Error: Failed to start DataBox Sidecar Engine at {:?}: {}", final_path, e);
                None
            }
        }
    }
}
