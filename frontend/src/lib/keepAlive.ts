// src/lib/keepalive.ts
import api from "../components/api";

declare global {
  interface Window {
    __keepAliveTimer?: number | null;
  }
}

export function startKeepAlive(intervalMs = 180_000) { // 3분
  // HMR/StrictMode 중복 방지
  if (window.__keepAliveTimer) return;
  window.__keepAliveTimer = window.setInterval(() => {
    api.get("/ping").catch(() => {});
  }, intervalMs);
}

export function stopKeepAlive() {
  if (window.__keepAliveTimer) {
    clearInterval(window.__keepAliveTimer);
    window.__keepAliveTimer = null;
  }
}
