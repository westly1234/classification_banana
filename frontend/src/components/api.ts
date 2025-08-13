// src/components/api.ts
import axios from "axios";

function resolveApiBase() {
  // ① Render가 주입하는 백엔드 호스트를 최우선
  const host = import.meta.env.VITE_API_HOST?.trim();
  if (host) return `https://${host}`;

  // ② (레거시) 수동으로 절대주소를 넣었을 때만 사용
  const legacy = import.meta.env.VITE_API_BASE?.trim();
  if (legacy) return legacy.replace(/\/+$/, "");

  // ③ 로컬
  return "http://localhost:8000";
}

export const API_BASE = resolveApiBase();

// 개발 중엔 한 번만 찍어보면 디버깅 쉬워요
if (import.meta.env.DEV) console.info("[API_BASE]", API_BASE);

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

// 요청 인터셉터 (토큰 부착)
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});

// 응답 인터셉터 (502 재시도 + 401 처리)
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const cfg: any = err.config || {};
    const status = err.response?.status;

    // 콜드스타트 1회 재시도
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