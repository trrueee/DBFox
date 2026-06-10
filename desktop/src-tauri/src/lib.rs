use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{AppHandle, Manager};

struct PythonEngine(Mutex<Option<Child>>);

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ConversationRecord {
    id: String,
    title: String,
    created_at: i64,
    updated_at: i64,
    context_tables_json: String,
    messages_json: String,
    artifacts_json: String,
}

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
        .invoke_handler(tauri::generate_handler![
            list_conversations,
            save_conversation,
            delete_conversation
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let _ = window;
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running DataBox");
}

#[tauri::command]
fn list_conversations(app: AppHandle) -> Result<Vec<ConversationRecord>, String> {
    let conn = open_conversation_db(&app)?;
    let mut stmt = conn
        .prepare(
            "SELECT id, title, created_at, updated_at, context_tables_json, messages_json, artifacts_json
             FROM conversations
             ORDER BY updated_at DESC",
        )
        .map_err(|err| err.to_string())?;

    let rows = stmt
        .query_map([], |row| {
            Ok(ConversationRecord {
                id: row.get(0)?,
                title: row.get(1)?,
                created_at: row.get(2)?,
                updated_at: row.get(3)?,
                context_tables_json: row.get(4)?,
                messages_json: row.get(5)?,
                artifacts_json: row.get(6)?,
            })
        })
        .map_err(|err| err.to_string())?;

    let mut conversations = Vec::new();
    for row in rows {
        conversations.push(row.map_err(|err| err.to_string())?);
    }
    Ok(conversations)
}

#[tauri::command]
fn save_conversation(app: AppHandle, conversation: ConversationRecord) -> Result<(), String> {
    let conn = open_conversation_db(&app)?;
    conn.execute(
        "INSERT INTO conversations (
            id, title, created_at, updated_at, context_tables_json, messages_json, artifacts_json
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
         ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            updated_at = excluded.updated_at,
            context_tables_json = excluded.context_tables_json,
            messages_json = excluded.messages_json,
            artifacts_json = excluded.artifacts_json",
        params![
            conversation.id,
            conversation.title,
            conversation.created_at,
            conversation.updated_at,
            conversation.context_tables_json,
            conversation.messages_json,
            conversation.artifacts_json,
        ],
    )
    .map_err(|err| err.to_string())?;
    Ok(())
}

#[tauri::command]
fn delete_conversation(app: AppHandle, id: String) -> Result<(), String> {
    let conn = open_conversation_db(&app)?;
    conn.execute("DELETE FROM conversations WHERE id = ?1", params![id])
        .map_err(|err| err.to_string())?;
    Ok(())
}

fn open_conversation_db(app: &AppHandle) -> Result<Connection, String> {
    let db_path = conversation_db_path(app)?;
    let conn = Connection::open(db_path).map_err(|err| err.to_string())?;
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            context_tables_json TEXT NOT NULL DEFAULT '[]',
            messages_json TEXT NOT NULL DEFAULT '[]',
            artifacts_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);",
    )
    .map_err(|err| err.to_string())?;
    Ok(conn)
}

fn conversation_db_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|err| err.to_string())?;
    Ok(dir.join("databox.sqlite3"))
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

        match Command::new(&final_path).current_dir(exe_dir).spawn() {
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
