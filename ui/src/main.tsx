import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
const App = lazy(() => location.pathname === '/cloud' || location.pathname === '/cloud/' ? import('./cloud/CloudStudio') : import('./App'))

// Mobile browsers require persistent notifications from a service worker;
// `new Notification()` is desktop-only on several engines, including iOS
// WebKit. This worker deliberately does not cache application assets, so a
// Maestro update can never strand users on an old UI bundle.
if ('serviceWorker' in navigator) {
  void navigator.serviceWorker.register('/maestro-sw.js', { scope: '/' }).catch(error => {
    console.warn('[Notifications] Service worker registration failed:', error)
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<p className="p-8 text-text-secondary">Loading ImageMaestro…</p>}><App /></Suspense>
  </StrictMode>,
)
