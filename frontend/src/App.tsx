import React, { useState } from 'react';
import { HashRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Sidebar from './components/Sidebar';
import AuthPage from './components/Auth';
import Dashboard from './components/Dashboard';
import Analyze from './components/Analyze';

// 보호된 라우트 (ProtectedRoute) 컴포넌트
import { Outlet } from 'react-router-dom'; // Outlet을 import 합니다.

const ProtectedRoute: React.FC = () => { // children prop은 더 이상 필요 없습니다.
    const { user, loading } = useAuth(); // AuthContext에서 user와 loading 상태를 가져옵니다.
    const location = useLocation();

    // AuthProvider가 로컬 스토리지에서 사용자 정보를 로딩 중일 때를 대비
    if (loading) {
        return <div>로딩 중...</div>; // 또는 스피너 컴포넌트
    }

    if (!user) { // 이제 user 객체 자체로 인증 여부를 판단합니다.
        return <Navigate to="/auth" state={{ from: location }} replace />;
    }

    return <Outlet />; // 인증되었다면, 자식 라우트들을 <Outlet> 위치에 렌더링합니다.
};

// 메인 레이아웃 컴포넌트
const MainLayout: React.FC<{
  children: React.ReactNode;
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
}> = ({ children, isSidebarOpen, toggleSidebar }) => (
  <div className="flex h-screen bg-brand-gray-100 relative">
    {/* ✅ Sidebar 먼저 렌더링 */}
    <Sidebar isOpen={isSidebarOpen} toggleSidebar={toggleSidebar} />

    {/* ✅ 햄버거 버튼 (사이드바 열려있을 땐 숨김) */}
    {!isSidebarOpen && (
      <button
        className="md:hidden absolute top-4 left-4 z-50 text-2xl text-gray-800"
        onClick={toggleSidebar}
      >
        ☰
      </button>
    )}

    {/* ✅ 메인 콘텐츠 */}
    <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
      {children}
    </main>
  </div>
);

export default function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const toggleSidebar = () => setIsSidebarOpen((prev) => !prev);

  return (
    <AuthProvider>
      <HashRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/auth" replace />} />
          <Route path="/auth" element={<AuthPage />} />

          <Route element={<ProtectedRoute />}>
            <Route
              path="/analyze"
              element={
                <MainLayout isSidebarOpen={isSidebarOpen} toggleSidebar={toggleSidebar}>
                  <Analyze />
                </MainLayout>
              }
            />
            <Route
              path="/dashboard"
              element={
                <MainLayout isSidebarOpen={isSidebarOpen} toggleSidebar={toggleSidebar}>
                  <Dashboard />
                </MainLayout>
              }
            />
          </Route>

          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </HashRouter>
    </AuthProvider>
  );
}