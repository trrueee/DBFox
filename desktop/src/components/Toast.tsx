import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { CheckCircle2, X, AlertTriangle, Info, XCircle } from "lucide-react";
import gsap from "gsap";

type ToastType = "success" | "error" | "warning" | "info";

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastCtx {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastCtx>({ toast: () => {} });

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  return useContext(ToastContext);
}

let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const [exitingIds, setExitingIds] = useState<Set<number>>(new Set());
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());
  const itemRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const remove = useCallback((id: number) => {
    if (exitingIds.has(id)) return;
    setExitingIds((prev) => new Set(prev).add(id));

    const el = itemRefs.current.get(id);
    if (el) {
      gsap.to(el, {
        opacity: 0,
        x: 40,
        duration: 0.25,
        ease: "power2.in",
        onComplete: () => {
          setItems((prev) => prev.filter((it) => it.id !== id));
          setExitingIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
          itemRefs.current.delete(id);
        },
      });
    } else {
      setItems((prev) => prev.filter((it) => it.id !== id));
      setExitingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }

    const t = timersRef.current.get(id);
    if (t) {
      clearTimeout(t);
      timersRef.current.delete(id);
    }
  }, [exitingIds]);

  const toast = useCallback(
    (message: string, type: ToastType = "info") => {
      const id = nextId++;
      setItems((prev) => [...prev.slice(-4), { id, type, message }]);
      const timer = setTimeout(() => remove(id), 4000);
      timersRef.current.set(id, timer);
    },
    [remove],
  );

  const setItemRef = useCallback((id: number, el: HTMLDivElement | null) => {
    if (el) {
      itemRefs.current.set(id, el);
      // Animate in
      gsap.fromTo(el, { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.4, ease: "back.out(1.4)" });
    }
  }, []);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
    };
  }, []);

  const icon = (type: ToastType) => {
    switch (type) {
      case "success":
        return <CheckCircle2 size={16} style={{ color: "var(--accent-green)" }} />;
      case "error":
        return <XCircle size={16} style={{ color: "var(--accent-red)" }} />;
      case "warning":
        return <AlertTriangle size={16} style={{ color: "var(--accent-amber)" }} />;
      case "info":
        return <Info size={16} style={{ color: "var(--accent-indigo)" }} />;
    }
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        style={{
          position: "fixed",
          bottom: 40,
          right: 24,
          zIndex: 9999,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {items.map((item) => (
          <div
            key={item.id}
            ref={(el) => setItemRef(item.id, el)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "12px 16px",
              background: "var(--bg-surface)",
              border: "1px solid var(--border-light)",
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--shadow-md)",
              fontSize: "0.85rem",
              color: "var(--text-primary)",
              minWidth: 200,
              maxWidth: 420,
              borderLeft: `3px solid ${item.type === "success" ? "var(--accent-green)" : item.type === "error" ? "var(--accent-red)" : item.type === "warning" ? "var(--accent-amber)" : "var(--accent-indigo)"}`,
            }}
          >
            {icon(item.type)}
            <span style={{ flex: 1 }}>{item.message}</span>
            <button
              onClick={() => remove(item.id)}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "var(--text-muted)",
                padding: 2,
                display: "flex",
              }}
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
