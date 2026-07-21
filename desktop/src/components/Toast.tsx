import { useCallback, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { allocateToastId, getToastRoot, ToastContext, type ToastType } from "./toastState";
import "./Toast.css";

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
}

function ToastIcon({ type }: { type: ToastType }) {
  switch (type) {
    case "success":
      return <CheckCircle2 className="dbfox-toast-icon-glyph" aria-hidden="true" />;
    case "error":
      return <XCircle className="dbfox-toast-icon-glyph" aria-hidden="true" />;
    case "warning":
      return <AlertTriangle className="dbfox-toast-icon-glyph" aria-hidden="true" />;
    case "info":
      return <Info className="dbfox-toast-icon-glyph" aria-hidden="true" />;
  }
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const remove = useCallback((id: number) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = allocateToastId();
    setItems((prev) => [...prev.slice(-4), { id, type, message }]);
  }, []);

  const toastStack = (
    <>
      {items.map((item) => (
        <ToastPrimitive.Root
          key={item.id}
          className={`dbfox-toast-root dbfox-toast-root--${item.type}`}
          duration={3500}
          role={item.type === "error" ? "alert" : "status"}
          aria-live={item.type === "error" ? "assertive" : "polite"}
          onOpenChange={(open) => {
            if (!open) remove(item.id);
          }}
          type={item.type === "error" ? "foreground" : "background"}
        >
          <span className="dbfox-toast-icon" aria-hidden="true">
            <ToastIcon type={item.type} />
          </span>
          <ToastPrimitive.Description asChild>
            <span className="dbfox-toast-message">{item.message}</span>
          </ToastPrimitive.Description>
          <ToastPrimitive.Close className="dbfox-toast-close" aria-label="关闭通知">
            <X className="dbfox-toast-close-icon" aria-hidden="true" />
          </ToastPrimitive.Close>
        </ToastPrimitive.Root>
      ))}
      <ToastPrimitive.Viewport className="dbfox-toast-viewport" />
    </>
  );

  return (
    <ToastContext.Provider value={{ toast }}>
      <ToastPrimitive.Provider swipeDirection="right" duration={3500}>
        {children}
        {getToastRoot() ? createPortal(toastStack, getToastRoot()!) : toastStack}
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}
