import { useEffect, useState } from "react";
import { Minus, Square, X } from "lucide-react";
import { FoxIcon } from "./brand/FoxIcon";
import { ThemeToggle } from "./ThemeToggle";
import "./TitleBar.css";

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

type Win = {
  minimize(): Promise<void>;
  toggleMaximize(): Promise<void>;
  close(): Promise<void>;
  isMaximized(): Promise<boolean>;
};

export default function TitleBar() {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!isTauriRuntime()) return;

    let cancelled = false;
    let unlisten: (() => void) | undefined;

    (async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const win = getCurrentWindow() as unknown as Win;

        if (cancelled) return;
        setMaximized(await win.isMaximized());

        unlisten = await (
          await import("@tauri-apps/api/window")
        ).getCurrentWindow().onResized(async () => {
          if (cancelled) return;
          setMaximized(await win.isMaximized());
        });
      } catch {
        // not in Tauri — silently ignore
      }
    })();

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  const handleMinimize = async () => {
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await (getCurrentWindow() as unknown as Win).minimize();
    } catch { /* ignore */ }
  };

  const handleToggleMaximize = async () => {
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      const win = getCurrentWindow() as unknown as Win;
      await win.toggleMaximize();
      setMaximized(await win.isMaximized());
    } catch { /* ignore */ }
  };

  const handleClose = async () => {
    try {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await (getCurrentWindow() as unknown as Win).close();
    } catch { /* ignore */ }
  };

  return (
    <div className="titlebar" data-tauri-drag-region>
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
