// src/components/api.ts
import axios from "axios";

function stripTrailingSlash(s: string) {
  return s.replace(/\/+$/, "");
}

function resolveApiBase() {
  // ① Render가 주입하는 호스트 우선
  const rawHost = import.meta.env.VITE_API_HOST?.trim();
  if (rawHost) {
    // host에 프로토콜이 있으면 그대로, 없으면 https 추가
    const url = rawHost.startsWith("http://") || rawHost.startsWith("https://")
      ? rawHost
      : `https://${rawHost}`;
    return stripTrailingSlash(url);
  }

  // ② 개발 모드일 때만 로컬 fallback 허용
  if (import.meta.env.DEV) {
    const base = import.meta.env.VITE_API_BASE?.trim();
    if (base) return stripTrailingSlash(base);
    return "http://localhost:8000";
  }

  // ③ 프로덕션이면 반드시 설정되어야 함 (localhost 강제 금지)
  throw new Error("API host is not configured in production build.");
}

export const API_BASE = resolveApiBase();
console.info("[API_BASE]", API_BASE); // ← 프로덕션에서도 한번 찍어서 확인

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const cfg: any = err.config || {};
    const status = err.response?.status;

    // 콜드스타트/네트워크 오류 1회 재시도
    if ((!err.response || status === 502) && !cfg.__retry) {
      cfg.__retry = true;
      await new Promise((r) => setTimeout(r, 1500));
      return api.request(cfg);
    }

    if (status === 401) {
      localStorage.removeItem("access_token");
      alert("세션이 만료되었습니다. 다시 로그인해주세요.");
      window.location.replace("/#/auth");
    }
    return Promise.reject(err);
  }
);

export default api;
