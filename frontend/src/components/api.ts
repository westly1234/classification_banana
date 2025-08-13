// src/components/api.ts
import axios from "axios";

function stripTrailingSlash(s: string) {
  return s.replace(/\/+$/, "");
}

function resolveApiBase() {
  // ① Render가 주입하는 호스트 우선
  const rawHost = import.meta.env.VITE_API_HOST?.trim();
  if (rawHost) {
    // host에 이미 프로토콜이 있으면 그대로, 없으면 https:// 붙임
    const url = rawHost.startsWith("http://") || rawHost.startsWith("https://")
      ? rawHost
      : `https://${rawHost}`;
    return stripTrailingSlash(url);
  }

  // ② 로컬 개발일 때만 VITE_API_BASE 사용
  if (import.meta.env.DEV) {
    const legacy = import.meta.env.VITE_API_BASE?.trim();
    if (legacy) return stripTrailingSlash(legacy);
    return "http://localhost:8000";
  }

  // ③ 프로덕션인데 값이 없으면 명확히 실패(디버깅 편의)
  throw new Error("API host is not configured in production build.");
}

export const API_BASE = resolveApiBase();
if (import.meta.env.DEV) console.info("[API_BASE]", API_BASE);

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

// --- 인터셉터 동일 ---
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
