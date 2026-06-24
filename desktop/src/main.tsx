import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastProvider } from './components/Toast'
import { ThemeProvider } from './hooks/useTheme'
import { TooltipProvider } from '@/components/ui/tooltip'
import { initEngineConfig, waitEngineHealth } from './lib/api/client'

// Hide the static boot indicator once React successfully mounts
const bootEl = document.getElementById('boot-indicator')

function renderEngineStartupError(error: unknown) {
  if (bootEl) bootEl.style.display = 'none'
  const root = document.getElementById('root')!
  const message = error instanceof Error ? error.message : 'Engine startup failed'
  root.textContent = ''
  const shell = document.createElement('div')
  shell.style.cssText = 'min-height:100vh;display:flex;align-items:center;justify-content:center;background:#111827;color:#f9fafb;font-family:Inter,system-ui,sans-serif;padding:24px;'
  const panel = document.createElement('div')
  panel.style.cssText = 'max-width:520px;'
  const title = document.createElement('h1')
  title.style.cssText = 'font-size:24px;line-height:1.2;margin:0 0 12px;'
  title.textContent = 'Engine startup failed'
  const body = document.createElement('p')
  body.style.cssText = 'font-size:14px;line-height:1.6;color:#d1d5db;margin:0;'
  body.textContent = message
  panel.append(title, body)
  shell.append(panel)
  root.append(shell)
}

initEngineConfig().then(() => waitEngineHealth()).then(() => {
  if (bootEl) bootEl.style.display = 'none'

  // Disable default context menu in production to make it feel like a native desktop app
  if (import.meta.env.PROD) {
    window.addEventListener('contextmenu', (e) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return;
      }
      e.preventDefault();
    });
  }

  // Listen to window focus/blur to toggle active/inactive visual classes on body
  window.addEventListener('focus', () => {
    document.body.classList.remove('window-inactive');
  });
  window.addEventListener('blur', () => {
    document.body.classList.add('window-inactive');
  });

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary>
        <ThemeProvider>
          <TooltipProvider>
            <ToastProvider>
              <App />
            </ToastProvider>
          </TooltipProvider>
        </ThemeProvider>
      </ErrorBoundary>
    </StrictMode>,
  )
}).catch(renderEngineStartupError)
