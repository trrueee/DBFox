import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
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

export function useToast() {
  return useContext(ToastContext);
}

let nextId = 0;

/** Container element inside the scaled canvas where toasts render (avoids viewport overflow). */
let toastRoot: HTMLElement | null = null;
export function setToastRoot(el: HTMLElement | null) { toastRoot = el; }

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
      const timer = setTimeout(() => remove(id), 3500);
      timersRef.current.set(id, timer);
    },
    [remove],
  );

  const setItemRef = useCallback((id: number, el: HTMLDivElement | null) => {
    if (el) {
      itemRefs.current.set(id, el);
      gsap.fromTo(el, { opacity: 0, x: 20, scale: 0.95 }, { opacity: 1, x: 0, scale: 1, duration: 0.3, ease: "back.out(1.3)" });
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
      case "success": return <CheckCircle2 size={15} style={{ color: "hsl(var(--success))", flexShrink: 0 }} />;
      case "error":   return <XCircle size={15} style={{ color: "hsl(var(--destructive))", flexShrink: 0 }} />;
      case "warning": return <AlertTriangle size={15} style={{ color: "hsl(var(--warning))", flexShrink: 0 }} />;
      case "info":    return <Info size={15} style={{ color: "hsl(var(--primary))", flexShrink: 0 }} />;
    }
  };

  const toastElement = items.length > 0 ? createPortal(
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      style={{
        position: "absolute",
        bottom: 20,
        right: 20,
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        pointerEvents: "none",
      }}
    >
      {items.map((item) => (
        <div
          key={item.id}
          ref={(el) => setItemRef(item.id, el)}
          role={item.type === "error" ? "alert" : "status"}
          aria-live={item.type === "error" ? "assertive" : "polite"}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px 14px",
            background: "hsl(var(--card))",
            border: "1px solid hsl(var(--border))",
            borderLeft: `3px solid ${
              item.type === "success" ? "hsl(var(--success))" :
              item.type === "error" ? "hsl(var(--destructive))" :
              item.type === "warning" ? "hsl(var(--warning))" :
              "hsl(var(--primary))"
            }`,
            borderRadius: "var(--radius)",
            boxShadow: "0 4px 16px rgba(0,0,0,0.08)",
            fontSize: "13px",
            color: "hsl(var(--foreground))",
            minWidth: 200,
            maxWidth: 400,
            pointerEvents: "auto",
          }}
        >
          {icon(item.type)}
          <span style={{ flex: 1, lineHeight: 1.4 }}>{item.message}</span>
          <button
            onClick={() => remove(item.id)}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "hsl(var(--muted-foreground))",
              padding: 2,
              display: "flex",
              opacity: 0.6,
              transition: "opacity 0.15s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.6")}
          >
            <X size={13} />
          </button>
        </div>
      ))}
    </div>,
    toastRoot || document.body,
  ) : null;

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {toastElement}
    </ToastContext.Provider>
  );
}
