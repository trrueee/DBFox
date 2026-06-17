import { useState, useEffect, useRef, type MouseEvent, useCallback } from "react";

const STORAGE_KEY = "dbfox-sidebar-width";

function loadWidth(): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const w = parseInt(raw, 10);
      if (w >= 180 && w <= 480) return w;
    }
  } catch { /* ignore */ }
  return 240;
}

export function useSidebarLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [width, setWidth] = useState(loadWidth);
  const resizingRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const handleResizeStart = useCallback((e: MouseEvent) => {
    e.preventDefault();
    resizingRef.current = { startX: e.clientX, startWidth: width };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [width]);

  useEffect(() => {
    const handleMouseMove = (e: globalThis.MouseEvent) => {
      if (!resizingRef.current) return;
      const delta = e.clientX - resizingRef.current.startX;
      const next = Math.max(180, Math.min(480, resizingRef.current.startWidth + delta));
      setWidth(next);
    };
    const handleMouseUp = () => {
      if (resizingRef.current) {
        try { localStorage.setItem(STORAGE_KEY, String(width)); } catch { /* ignore */ }
      }
      resizingRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [width]);

  const toggleCollapse = useCallback(() => setCollapsed((v) => !v), []);

  return { collapsed, width, handleResizeStart, toggleCollapse };
}
