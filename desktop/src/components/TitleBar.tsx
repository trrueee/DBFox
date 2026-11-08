import { useEffect, useState, type ReactNode } from "react";
import {
  CopyIcon,
  MinusIcon,
  SquareIcon,
  XIcon,
} from "@/components/icons";
import {
  closeDesktopWindow,
  getDesktopWindowMaximized,
  isEngineDesktopHost,
  minimizeDesktopWindow,
  subscribeDesktopWindowState,
  toggleMaximizeDesktopWindow,
} from "../lib/desktopHost";
import "./TitleBar.css";

export default function TitleBar({ title, titleHint, actions, leading }: { title?: string; titleHint?: string; actions?: ReactNode; leading?: ReactNode }) {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!isEngineDesktopHost()) return;
    let cancelled = false;
    let observedState = false;
    const unlisten = subscribeDesktopWindowState(value => {
      observedState = true;
      if (!cancelled) setMaximized(value);
    });
    void getDesktopWindowMaximized().then(value => {
      if (!cancelled && !observedState) setMaximized(value);
    }).catch(() => { /* The subscription remains authoritative if the initial read fails. */ });
    return () => { cancelled = true; unlisten(); };
  }, []);

  const handleMinimize = async () => { try { await minimizeDesktopWindow(); } catch { /* ignore */ } };
  const handleToggleMaximize = async () => { try { setMaximized(await toggleMaximizeDesktopWindow()); } catch { /* ignore */ } };
  const handleClose = async () => { try { await closeDesktopWindow(); } catch { /* ignore */ } };

  return (
    <header className="titlebar" onDoubleClick={handleToggleMaximize}>
      {title ? <div className="titlebar-heading">{leading}<h1 className="titlebar-title" title={titleHint || title}>{title}</h1>
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
              <MinusIcon size={14} aria-hidden="true" />
            </button>
            <button
              className="titlebar-btn"
              onClick={handleToggleMaximize}
              title={maximized ? "还原" : "最大化"}
              aria-label={maximized ? "还原" : "最大化"}
            >
              {maximized
                ? <CopyIcon size={14} aria-hidden="true" />
                : <SquareIcon size={14} aria-hidden="true" />}
            </button>
            <button
              className="titlebar-btn titlebar-btn-close"
              onClick={handleClose}
              title="关闭"
              aria-label="关闭"
            >
              <XIcon size={16} aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
