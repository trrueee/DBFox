import { useEffect, useState, type ReactNode } from "react";
import { Copy, Minus, Square, X } from "lucide-react";
import {
  closeDesktopWindow,
  getDesktopWindowMaximized,
  isEngineDesktopHost,
  minimizeDesktopWindow,
  subscribeDesktopWindowState,
  toggleMaximizeDesktopWindow,
} from "../lib/desktopHost";
import "./TitleBar.css";

export default function TitleBar({ title, titleHint, actions }: { title?: string; titleHint?: string; actions?: ReactNode }) {
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
    <header className="titlebar" onDoubleClick={handleToggleMaximize}>
      {title ? <div className="titlebar-heading"><h1 className="titlebar-title" title={titleHint || title}>{title}</h1>
        <div className="titlebar-actions" onDoubleClick={event => event.stopPropagation()}>{actions}</div>
      </div> : null}
      <div className="titlebar-controls" onDoubleClick={(event) => event.stopPropagation()}>
        {isEngineDesktopHost() && (
          <div className="titlebar-window-controls">
            <button
              className="titlebar-btn"
              onClick={handleMinimize}
              title="最小化"
              aria-label="最小化"
            >
              <Minus size={14} strokeWidth={1.5} aria-hidden="true" />
            </button>
            <button
              className="titlebar-btn"
              onClick={handleToggleMaximize}
              title={maximized ? "还原" : "最大化"}
              aria-label={maximized ? "还原" : "最大化"}
            >
              {maximized
                ? <Copy size={14} strokeWidth={1.5} aria-hidden="true" />
                : <Square size={14} strokeWidth={1.5} aria-hidden="true" />}
            </button>
            <button
              className="titlebar-btn titlebar-btn-close"
              onClick={handleClose}
              title="关闭"
              aria-label="关闭"
            >
              <X size={16} strokeWidth={1.5} aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
