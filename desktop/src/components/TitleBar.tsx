import { useEffect, useState } from "react";
import { Minus, Square, X } from "lucide-react";
import { FoxIcon } from "./brand/FoxIcon";
import { ThemeToggle } from "./ThemeToggle";
import "./TitleBar.css";

interface TauriWindow {
  isMaximized(): Promise<boolean>;
  minimize(): Promise<void>;
  toggleMaximize(): Promise<void>;
  close(): Promise<void>;
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

let _tauriWindow: (() => Promise<TauriWindow>) | null = null;

async function getTauriWindow(): Promise<TauriWindow | null> {
  if (!isTauriRuntime()) return null;
  if (!_tauriWindow) {
    try {
      const mod = await import("@tauri-apps/api/window");
      _tauriWindow = () => mod.getCurrentWindow() as unknown as Promise<TauriWindow>;
    } catch {
      return null;
    }
  }
  return _tauriWindow!();
}

export default function TitleBar() {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;

    (async () => {
      const win = await getTauriWindow();
      if (!win || cancelled) return;
      setMaximized(await win.isMaximized());

      try {
        const mod = await import("@tauri-apps/api/window");
        unlisten = await mod.getCurrentWindow().onResized(async () => {
          if (cancelled) return;
          setMaximized(await win.isMaximized());
        });
      } catch { /* ignore */ }
    })();

    return () => { cancelled = true; unlisten?.(); };
  }, []);

  const handleMinimize = async () => { try { (await getTauriWindow())?.minimize(); } catch { /* ignore */ } };
  const handleToggleMaximize = async () => { try { const w = await getTauriWindow(); if (w) { await w.toggleMaximize(); setMaximized(await w.isMaximized()); } } catch { /* ignore */ } };
  const handleClose = async () => { try { (await getTauriWindow())?.close(); } catch { /* ignore */ } };

  return (
    <div className="titlebar" data-tauri-drag-region onDoubleClick={handleToggleMaximize}>
      <span className="titlebar-brand">
        <span className="titlebar-logo">
          <FoxIcon variant="app" size={20} />
        </span>
        <span className="titlebar-title">DBFox</span>
      </span>
      <div className="titlebar-controls" style={{ gap: "8px" }}>
        <ThemeToggle />
        {isTauriRuntime() && (
          <div style={{ display: "flex", alignItems: "center", gap: "2px" }}>
            <button
              className="titlebar-btn"
              onClick={handleMinimize}
              title="最小化"
            >
              <Minus size={14} />
            </button>
            <button
              className="titlebar-btn"
              onClick={handleToggleMaximize}
              title={maximized ? "还原" : "最大化"}
            >
              <Square size={12} />
            </button>
            <button
              className="titlebar-btn titlebar-btn-close"
              onClick={handleClose}
              title="关闭"
            >
              <X size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
