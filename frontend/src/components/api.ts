// src/components/api.ts
import axios from "axios";

function resolveApiBase() {
  // ① 절대주소 명시 (프로덕션/개발 공통 허용)
  const explicit = import.meta.env.VITE_API_BASE?.trim();
  if (explicit) return explicit.replace(/\/+$/, "");

  // ② Render가 연결해 주입하는 host
  const host = import.meta.env.VITE_API_HOST?.trim();
  if (host) return `https://${host}`;

  // ③ 개발 기본값
  if (import.meta.env.DEV) return "http://localhost:8000";

  // ④ 프로덕션에서 빠질 수 없게 가드
  throw new Error("API host is not configured in production build.");
}

export const API_BASE = resolveApiBase();
if (import.meta.env.DEV) console.info("[API_BASE]", API_BASE);

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
