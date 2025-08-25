// src/lib/keepalive.ts
import api from "../components/api";

declare global { interface Window { __keepAliveStopper?: () => void } }

export function startKeepAlive(baseIntervalMs = 180_000) {
  if (window.__keepAliveStopper) return;

  let stopped = false;
  let inFlight = false;
  let backoff = 0;
  let visHandler: (() => void) | null = null;
  let timer: number | null = null;

  const jitter = () => Math.floor(Math.random() * 15_000); // 0~15s
  const nextDelay = () => baseIntervalMs + jitter() + Math.min(backoff * 10_000, 60_000);

  const schedule = () => {
    if (stopped) return;
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(tick, nextDelay());
  };

  const tick = async () => {
    if (stopped) return;
    if (document.visibilityState !== "visible") { schedule(); return; }
    if (inFlight) { schedule(); return; }
    inFlight = true;
    try {
      await api.get("/healthz", {
        params: { t: Date.now() },
        timeout: 3500,
        validateStatus: () => true, // 2xx 아니어도 ok
      });
      backoff = 0;
    } catch {
      backoff += 1; // 실패 누적 → 백오프 증가
    } finally {
      inFlight = false;
      schedule();
    }
  };

  visHandler = () => { if (!stopped) tick(); };
  document.addEventListener("visibilitychange", visHandler);

  schedule();

  window.__keepAliveStopper = () => {
    stopped = true;
    if (timer) window.clearTimeout(timer);
    timer = null;
    if (visHandler) document.removeEventListener("visibilitychange", visHandler);
    window.__keepAliveStopper = undefined;
  };
}

export function stopKeepAlive() {
  window.__keepAliveStopper?.();
}