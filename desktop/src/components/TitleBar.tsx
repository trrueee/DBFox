import { useEffect, useState } from "react";
import { Minus, Square, X } from "lucide-react";
import { FoxIcon } from "./brand/FoxIcon";
import { ThemeToggle } from "./ThemeToggle";
import {
  closeDesktopWindow,
  getDesktopWindowMaximized,
  isEngineDesktopHost,
  minimizeDesktopWindow,
  subscribeDesktopWindowState,
  toggleMaximizeDesktopWindow,
} from "../lib/desktopHost";
import "./TitleBar.css";

export default function TitleBar() {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;

    (async () => {
      if (!isEngineDesktopHost() || cancelled) return;
      setMaximized(await getDesktopWindowMaximized());
      unlisten = await subscribeDesktopWindowState((value) => {
        if (!cancelled) setMaximized(value);
      });
    })();

    return () => { cancelled = true; unlisten?.(); };
  }, []);

  const handleMinimize = async () => { try { await minimizeDesktopWindow(); } catch { /* ignore */ } };
  const handleToggleMaximize = async () => { try { setMaximized(await toggleMaximizeDesktopWindow()); } catch { /* ignore */ } };
  const handleClose = async () => { try { await closeDesktopWindow(); } catch { /* ignore */ } };

  return (
    <div className="titlebar" onDoubleClick={handleToggleMaximize}>
      <span className="titlebar-brand">
        <span className="titlebar-logo">
          <FoxIcon variant="app" size={24} />
        </span>
        <span className="titlebar-title">DBFox</span>
      </span>
      <div className="titlebar-controls titlebar-controls--spacious">
        <ThemeToggle />
        {isEngineDesktopHost() && (
          <div className="titlebar-window-controls">
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
              <Square size={14} />
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
