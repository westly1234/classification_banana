// AuthContext.tsx 전체 코드

import React, { createContext, useContext, useState, useEffect } from "react";

interface AuthContextType {
  user: { name: string; email: string } | null;
  loading: boolean; // 로딩 상태 추가
  login: (userData: { name: string; email: string }) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<{ name: string; email: string } | null>(null);
  const [loading, setLoading] = useState(true); // 초기 상태는 로딩 중

  useEffect(() => {
    try {
        const savedUser = localStorage.getItem("user");
        const token = localStorage.getItem("access_token");

        if (savedUser && token) {
            setUser(JSON.parse(savedUser));
        }
    } catch (error) {
        console.error("사용자 정보 복원 실패", error);
        setUser(null); // 에러 발생 시 확실하게 로그아웃 처리
    } finally {
        setLoading(false); // 정보 복원 시도 후 로딩 상태 해제
    }
  }, []);

  const login = (userData: { name: string; email: string }) => {
    setUser(userData);
    localStorage.setItem("user", JSON.stringify(userData));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem("user");
    localStorage.removeItem("access_token");
  };

  const value = { user, loading, login, logout };

  return (
    <AuthContext.Provider value={value}>
      {!loading && children} {/* 로딩이 끝나면 자식 컴포넌트를 렌더링 */}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
};