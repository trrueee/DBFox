import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import "./styles/tokens.css";
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

const DesignLab = import.meta.env.DEV
  ? lazy(() => import("./design-lab/DesignLab").then((module) => ({
    default: module.DesignLab,
  })))
  : null;

const SHOW_DESIGN_LAB = import.meta.env.DEV
  && new URLSearchParams(window.location.search).get("design-lab") === "1";

function renderApplication(): void {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <TooltipProvider>
              <ToastProvider>
                {SHOW_DESIGN_LAB && DesignLab ? (
                  <Suspense fallback={null}>
                    <DesignLab />
                  </Suspense>
                ) : (
                  <EngineStartupGate>
                    <App />
                  </EngineStartupGate>
                )}
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
