// src/lib/keepalive.ts
import api from "../components/api";

declare global {
  interface Window {
    __keepAliveStopper?: () => void;   // 정리용 핸들
  }
}

export function startKeepAlive(baseIntervalMs = 180_000) {
  // 중복 방지
  if (window.__keepAliveStopper) return;

  let stopped = false;
  let inFlight = false;
  let backoff = 0; // 연속 실패 횟수
  let visHandler: (() => void) | null = null;
  let timer: number | null = null;

  const jitter = () => Math.floor(Math.random() * 15_000); // 0~15s
  const nextDelay = () => baseIntervalMs + jitter() + Math.min(backoff * 10_000, 60_000);

  const tick = async () => {
    if (stopped) return;
    if (document.visibilityState !== "visible") {
      schedule();
      return;
    }
    if (inFlight) {         // 이전 요청 완료 대기
      schedule();
      return;
    }
    inFlight = true;
    try {
      // 가벼운 HEAD 핑 (FastAPI는 기본적으로 HEAD를 GET 처리로 지원)
      await api.head("/ping", { params: { t: Date.now() } });
      backoff = 0;
    } catch {
      // 실패 시 백오프 증가
      backoff += 1;
    } finally {
      inFlight = false;
      schedule();
    }
  };

  const schedule = () => {
    if (stopped) return;
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(tick, nextDelay());
  };

  // 가시성 변경 시 즉시 한 번 쿨하게 때림
  visHandler = () => {
    if (stopped) return;
    tick();
  };
  document.addEventListener("visibilitychange", visHandler);

  // 첫 스케줄
  schedule();

  // 정리 함수 저장
  window.__keepAliveStopper = () => {
    stopped = true;
    if (timer) window.clearTimeout(timer);
    timer = null;
    if (visHandler) {
      document.removeEventListener("visibilitychange", visHandler);
      visHandler = null;
    }
    window.__keepAliveStopper = undefined;
  };
}

export function stopKeepAlive() {
  if (window.__keepAliveStopper) {
    window.__keepAliveStopper();
  }
}