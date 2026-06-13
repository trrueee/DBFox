import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastProvider } from './components/Toast'
import { ThemeProvider } from './hooks/useTheme'
import { TooltipProvider } from '@/components/ui/tooltip'

// Hide the static boot indicator once React successfully mounts
const bootEl = document.getElementById('boot-indicator')
if (bootEl) bootEl.style.display = 'none'

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
