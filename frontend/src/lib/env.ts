// src/lib/env.ts
function sanitize(input?: string) {
  const v = (input ?? "").trim();
  if (!v) return "";
  return /^https?:\/\//i.test(v) ? v.replace(/\/+$/, "") : `https://${v}`;
}

export function resolveApiBase() {
  // 1) Render가 주입하는 백엔드 호스트를 최우선
  const host = sanitize(import.meta.env.VITE_API_HOST as string | undefined);
  if (host) return host;

  // 2) (레거시) 절대주소를 직접 넣었을 때만 사용
  const legacy = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
  const legacyTrim = legacy.trim();
  if (legacyTrim) return legacyTrim.replace(/\/+$/, "");

  // 3) 로컬
  return "http://localhost:8000";
}

export const API_BASE = resolveApiBase();

// 개발 중 디버깅
if (import.meta.env.DEV) console.info("[API_BASE]", API_BASE);
