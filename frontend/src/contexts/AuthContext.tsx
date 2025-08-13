// AuthContext.tsx
import React, { createContext, useContext, useEffect, useState } from "react";

type User = { email: string; nickname?: string } | null;
type Ctx = { user: User; loading: boolean; login: (t: string) => void; logout: () => void };

const AuthContext = createContext<Ctx | null>(null);

function decode(token: string): { sub?: string; nickname?: string; exp?: number } | null {
  try {
    const b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    return JSON.parse(atob(padded));
  } catch {
    return null;
  }
}
function isExpired(exp?: number) {
  if (!exp) return true;
  return Date.now() >= exp * 1000;
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);
  
  const applyToken = (tok: string | null) => {
    if (!tok) {
      setUser(null);
      return;
    }
    const p = decode(tok);
    if (!p || !p.sub || isExpired(p.exp)) {
      localStorage.removeItem("access_token"); // 불량/만료 토큰 즉시 제거
      setUser(null);
      return;
    }
    setUser({ email: p.sub, nickname: p.nickname });
  };

  useEffect(() => {
    applyToken(localStorage.getItem("access_token"));
    setLoading(false);

    // 다른 탭과 동기화
    const onStorage = () => applyToken(localStorage.getItem("access_token"));
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const login = (token: string) => {
    localStorage.setItem("access_token", token);
    applyToken(token);
  };
  const logout = () => {
    localStorage.removeItem("access_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {!loading && children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
};