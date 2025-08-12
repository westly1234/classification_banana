// src/components/api.ts
import axios from "axios";

function resolveApiBase() {
  const legacy = import.meta.env.VITE_API_BASE as string | undefined;
  if (legacy && legacy.trim()) return legacy.replace(/\/+$/, "");

  const host = import.meta.env.VITE_API_HOST as string | undefined; // Render 자동 주입
  if (host && host.trim()) return `https://${host}`;

  return "http://localhost:8000"; // 로컬 기본값
}

export const API_BASE = resolveApiBase();   // ← 이 줄 추가

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

// 요청 인터셉터: Authorization 자동 부착
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("access_token");
    if (token) {
      // headers가 undefined일 수 있으니 안전하게
      config.headers = config.headers ?? {};
      (config.headers as any).Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 응답 인터셉터: 502 한 번 재시도 + 401 처리
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const cfg: any = err.config || {};
    const status = err.response?.status;

    // 🔁 콜드스타트(502) 1회 재시도
    if ((!err.response || status === 502) && !cfg.__retry) {
      cfg.__retry = true;
      await new Promise((r) => setTimeout(r, 1500));
      return api.request(cfg);
    }

    // 🔐 인증 만료
    if (status === 401) {
      localStorage.removeItem("access_token");
      alert("세션이 만료되었습니다. 다시 로그인해주세요.");
      window.location.replace("/#/auth"); // ✅ HashRouter 경로
      return Promise.reject(err); // ⬅️ 호출부로 명확히 에러를 전파 (✅)
    }

    return Promise.reject(err);
  }
);

export default api;
