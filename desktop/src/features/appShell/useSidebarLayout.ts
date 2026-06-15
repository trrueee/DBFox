import { useState, useEffect, useRef, type MouseEvent, useCallback } from "react";

export function useSidebarLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [width, setWidth] = useState(240);
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
  }, []);

  const toggleCollapse = useCallback(() => setCollapsed((v) => !v), []);

  return { collapsed, width, handleResizeStart, toggleCollapse };
}
