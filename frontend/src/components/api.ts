// src/components/api.ts
import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

/** 배이스 URL 결정 */
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

/** 인증 불필요/공개 엔드포인트 프리픽스 */
export const NO_AUTH_PREFIXES = ["/tasks/", "/ping", "/settings", "/results/"];

/** 주어진 URL이 공개 경로인지 판별 */
function isPublicPath(url?: string): boolean {
  try {
    const path = new URL(url ?? "", API_BASE).pathname;
    return NO_AUTH_PREFIXES.some((p) => path.startsWith(p));
  } catch {
    const path = (url ?? "").toString();
    return NO_AUTH_PREFIXES.some((p) => path.startsWith(p));
  }
}

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  withCredentials: false, // 서버 CORS에서 credentials 안 쓰므로 false
});

/** 요청 인터셉터: 공개 URL은 Authorization 제거, 그 외는 토큰 부착 */
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const url = config.url ?? "";
  if (isPublicPath(url)) {
    if (config.headers) {
      delete (config.headers as any).Authorization;
    }
  } else {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers = config.headers ?? {};
      (config.headers as any).Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

/** 응답 인터셉터: 공개 URL의 401은 로그아웃하지 않음 */
api.interceptors.response.use(
  (res) => res,
  async (err: AxiosError) => {
    const cfg: any = err.config || {};
    const status = err.response?.status;
    const publicUrl = isPublicPath(cfg?.url);

    // 네트워크/일시 오류 1회 재시도
    if ((!err.response || status === 502) && !cfg.__retry) {
      cfg.__retry = true;
      await new Promise((r) => setTimeout(r, 1500));
      return api.request(cfg);
    }

    // 보호 경로의 401만 세션 만료 처리
    if (status === 401 && !publicUrl) {
      localStorage.removeItem("access_token");
      alert("세션이 만료되었습니다. 다시 로그인해주세요.");
      window.location.replace("/#/auth");
    }

    return Promise.reject(err);
  }
);

export default api;