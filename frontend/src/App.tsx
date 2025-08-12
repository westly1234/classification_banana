// src/App.tsx
import React, { useEffect, useState, Suspense } from 'react';
import { HashRouter, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import AuthPage from './components/Auth'; // 이건 유지 (문제시 이것도 스텁으로 교체 가능)

// 🔒 인증 보호 라우트
const ProtectedRoute: React.FC = () => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div>로딩 중...</div>;
  if (!user) return <Navigate to="/auth" state={{ from: location }} replace />;
  return <Outlet />;
};

// ✅ 의심 라이브러리 안 쓰는 안전한 레이아웃 & 페이지 스텁
const MainLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ minHeight: '100vh', padding: 16 }}>
    <header style={{ marginBottom: 12, fontWeight: 700 }}>Banana-lytics (safe mode)</header>
    <main>{children}</main>
  </div>
);

// ⛳️ 스텁 페이지 (video-react / recharts / react-player 일절 사용 X)
const SafeAnalyze: React.FC = () => <div>Analyze (safe stub)</div>;
const SafeDashboard: React.FC = () => <div>Dashboard (safe stub)</div>;

export default function App() {
  const [warmed, setWarmed] = useState(false);

  // API 핑도 환경변수 없으면 스킵
  useEffect(() => {
    const base = (import.meta as any).env?.VITE_API_BASE;
    if (!base) return;
    fetch(`${base}/ping`).then(() => setWarmed(true)).catch(() => setWarmed(true));
  }, []);

  return (
    <AuthProvider>
      <HashRouter>
        <Suspense fallback={<div>로딩 중...</div>}>
          <Routes>
            <Route path="/" element={<Navigate to="/auth" replace />} />
            <Route path="/auth" element={<AuthPage />} />

            <Route element={<ProtectedRoute />}>
              <Route
                path="/analyze"
                element={
                  <MainLayout>
                    <SafeAnalyze />
                  </MainLayout>
                }
              />
              <Route
                path="/dashboard"
                element={
                  <MainLayout>
                    <SafeDashboard />
                  </MainLayout>
                }
              />
            </Route>

            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </Suspense>
      </HashRouter>
    </AuthProvider>
  );
}