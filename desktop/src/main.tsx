import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import "./csp-safe.css";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { EngineStartupGate } from "./components/EngineStartupGate";
import { ToastProvider } from "./components/Toast";
import { ThemeProvider } from "./hooks/useTheme";
import { TooltipProvider } from "@/components/ui/tooltip";
import { hideBootIndicator } from "./boot";
import { installCspStyleNoncePropagation } from "./lib/cspStyleNonce";

function renderApplication(): void {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ErrorBoundary>
        <ThemeProvider>
          <TooltipProvider>
            <ToastProvider>
              <EngineStartupGate>
                <App />
              </EngineStartupGate>
            </ToastProvider>
          </TooltipProvider>
        </ThemeProvider>
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
  installCspStyleNoncePropagation();
  installWindowVisualStateListeners();
  renderApplication();
  hideBootIndicator();
}

startApplication();
