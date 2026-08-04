use std::fmt;
use std::path::PathBuf;
use std::sync::mpsc;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
use std::process::{Command, Stdio};
use tauri::{AppHandle, Runtime};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

use crate::sidecar_log::SidecarLog;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

fn python_dev_engine_args() -> [&'static str; 3] {
    ["-m", "engine.main", "--no-reload"]
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct EngineExit {
    code: Option<i32>,
    signal: Option<i32>,
}

impl fmt::Display for EngineExit {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match (self.code, self.signal) {
            (Some(code), _) => write!(formatter, "exit code {code}"),
            (None, Some(signal)) => write!(formatter, "signal {signal}"),
            (None, None) => formatter.write_str("unknown exit status"),
        }
    }
}

/// The only process adapter exposed to RuntimeSupervisor.
///
/// Tauri's official Shell plugin owns externalBin resolution, process creation,
/// stdout/stderr framing and exit observation. DBFox keeps its domain lifecycle
/// and the verified Windows PyInstaller process-tree termination policy.
#[derive(Debug)]
pub(crate) struct EngineChild {
    child: Option<CommandChild>,
    pid: u32,
    termination: mpsc::Receiver<Result<EngineExit, String>>,
    observed_exit: Option<EngineExit>,
}

impl EngineChild {
    pub(crate) fn pid(&self) -> u32 {
        self.pid
    }

    pub(crate) fn try_wait(&mut self) -> Result<Option<EngineExit>, String> {
        if let Some(exit) = &self.observed_exit {
            return Ok(Some(exit.clone()));
        }
        match self.termination.try_recv() {
            Ok(Ok(exit)) => {
                self.observed_exit = Some(exit.clone());
                Ok(Some(exit))
            }
            Ok(Err(error)) => Err(error),
            Err(mpsc::TryRecvError::Empty) => Ok(None),
            Err(mpsc::TryRecvError::Disconnected) => {
                Err("Sidecar event stream closed before a termination event".to_string())
            }
        }
    }

    pub(crate) fn stop(mut self) {
        if self.child.is_none() {
            return;
        }

        #[cfg(target_os = "windows")]
        {
            // PyInstaller one-file executables create a wrapper and an inner
            // process. CommandChild::kill targets only the wrapper.
            let status = Command::new("taskkill")
                .args(["/PID", &self.pid.to_string(), "/T", "/F"])
                .creation_flags(CREATE_NO_WINDOW)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
            if status.map(|status| status.success()).unwrap_or(false) {
                self.child.take();
                return;
            }
        }

        if let Some(child) = self.child.take() {
            let _ = child.kill();
        }
    }

    #[cfg(test)]
    pub(crate) fn test_running() -> (Self, mpsc::Sender<Result<EngineExit, String>>) {
        let (sender, termination) = mpsc::channel();
        (
            Self {
                child: None,
                pid: 0,
                termination,
                observed_exit: None,
            },
            sender,
        )
    }

    #[cfg(test)]
    pub(crate) fn test_exited(code: i32) -> Self {
        let (child, sender) = Self::test_running();
        sender
            .send(Ok(EngineExit {
                code: Some(code),
                signal: None,
            }))
            .expect("test termination receiver should remain connected");
        child
    }
}

pub(crate) fn spawn_python_engine<R: Runtime>(
    app: &AppHandle<R>,
    token: &str,
    log: &SidecarLog,
) -> Result<(EngineChild, mpsc::Receiver<String>), String> {
    let command = if cfg!(debug_assertions) {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|path| path.parent())
            .ok_or_else(|| "Unable to resolve DBFox repository root".to_string())?
            .to_path_buf();
        app.shell()
            .command("python")
            .args(python_dev_engine_args())
            .env("PYTHONPATH", &root)
            .env("DBFOX_ENGINE_PORT", "0")
            .env("DBFOX_ENGINE_TOKEN", token)
            .current_dir(root)
    } else {
        let executable_directory = std::env::current_exe()
            .map_err(|error| format!("Unable to resolve current executable: {error}"))?
            .parent()
            .ok_or_else(|| "Unable to resolve executable directory".to_string())?
            .to_path_buf();
        app.shell()
            .sidecar("dbfox-engine")
            .map_err(|error| format!("Unable to resolve bundled DBFox Sidecar: {error}"))?
            .env("DBFOX_ENGINE_PORT", "0")
            .env("DBFOX_ENGINE_TOKEN", token)
            .current_dir(executable_directory)
    };

    let (events, child) = command.spawn().map_err(|error| {
        let message = format!("Failed to start DBFox Python engine: {error}");
        log.error(&message);
        message
    })?;
    let pid = child.pid();
    let (stdout_sender, stdout_lines) = mpsc::channel();
    let (termination_sender, termination) = mpsc::channel();
    let event_log = *log;

    tauri::async_runtime::spawn(async move {
        let mut events = events;
        let mut terminated = false;
        while let Some(event) = events.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => match String::from_utf8(bytes) {
                    Ok(line) => {
                        let _ = stdout_sender.send(line);
                    }
                    Err(error) => event_log.error(&format!(
                        "Python engine stdout was not valid UTF-8 ({} bytes)",
                        error.as_bytes().len()
                    )),
                },
                CommandEvent::Stderr(bytes) => event_log.error(&format!(
                    "Python engine stderr emitted {} bytes of diagnostic output.",
                    bytes.len()
                )),
                CommandEvent::Error(error) => {
                    event_log.error(&format!("Python engine process observer failed: {error}"));
                }
                CommandEvent::Terminated(payload) => {
                    terminated = true;
                    let _ = termination_sender.send(Ok(EngineExit {
                        code: payload.code,
                        signal: payload.signal,
                    }));
                    break;
                }
                _ => {}
            }
        }
        if !terminated {
            let _ = termination_sender.send(Err(
                "Sidecar event stream closed before a termination event".to_string(),
            ));
        }
    });

    Ok((
        EngineChild {
            child: Some(child),
            pid,
            termination,
            observed_exit: None,
        },
        stdout_lines,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exit_status_is_stable_after_observation() {
        let mut child = EngineChild::test_exited(7);
        let first = child.try_wait().expect("exit observation should succeed");
        let second = child
            .try_wait()
            .expect("cached exit should remain available");
        assert_eq!(first, second);
        assert_eq!(first.expect("exit should exist").to_string(), "exit code 7");
    }

    #[test]
    fn running_child_has_no_exit_until_terminated() {
        let (mut child, _sender) = EngineChild::test_running();
        assert!(child
            .try_wait()
            .expect("observation should succeed")
            .is_none());
    }

    #[test]
    fn dev_engine_args_disable_python_reload() {
        assert_eq!(
            python_dev_engine_args(),
            ["-m", "engine.main", "--no-reload"]
        );
    }
}
