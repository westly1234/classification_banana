// src/lib/keepalive.ts
import api from "../components/api";

declare global {
  interface Window { __keepAliveTimer?: number | null; }
}

export function startKeepAlive(intervalMs = 180_000) {
  if (window.__keepAliveTimer) return; // 중복 방지

  const tick = () => {
    if (document.visibilityState !== "visible") return;
    api.get("/ping", { params: { t: Date.now() } }).catch(() => {});
  };

  // 가벼운 지터(동시 타격 방지)
  const jitter = () => Math.floor(Math.random() * 15_000);

  window.__keepAliveTimer = window.setInterval(tick, intervalMs + jitter());
  document.addEventListener("visibilitychange", tick);
}

export function stopKeepAlive() {
  if (window.__keepAliveTimer) {
    clearInterval(window.__keepAliveTimer);
    window.__keepAliveTimer = null;
  }
}