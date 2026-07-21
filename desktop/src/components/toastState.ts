import { createContext, useContext } from "react";

export type ToastType = "success" | "error" | "warning" | "info";

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

export const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

let nextId = 0;
let toastRoot: HTMLElement | null = null;

export function allocateToastId() {
  return nextId++;
}

export function setToastRoot(element: HTMLElement | null) {
  toastRoot = element;
}

export function getToastRoot() {
  return toastRoot;
}
