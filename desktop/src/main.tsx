import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App.tsx";
import "./csp-safe.css";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { EngineStartupGate } from "./components/EngineStartupGate";
import { ToastProvider } from "./components/Toast";
import { ThemeProvider } from "./hooks/useTheme";
import { TooltipProvider } from "@/components/ui/tooltip";
import { hideBootIndicator } from "./boot";
import { queryClient } from "./lib/queryClient";

function renderApplication(): void {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <TooltipProvider>
              <ToastProvider>
                <EngineStartupGate>
                  <App />
                </EngineStartupGate>
              </ToastProvider>
            </TooltipProvider>
          </ThemeProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </StrictMode>,
  );
}

function installWindowVisualStateListeners(): void {
  if (import.meta.env.PROD) {
    window.addEventListener("contextmenu", (event) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      event.preventDefault();
    });
  }

  window.addEventListener("focus", () => document.body.classList.remove("window-inactive"));
  window.addEventListener("blur", () => document.body.classList.add("window-inactive"));
}

function startApplication(): void {
  installWindowVisualStateListeners();
  renderApplication();
  hideBootIndicator();
}

startApplication();
