// src/App.tsx
import React, { useState, useEffect, Suspense } from 'react';
import { HashRouter, Routes, Route, Navigate, useLocation, Outlet } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Sidebar from './components/Sidebar';
import AuthPage from './components/Auth';

// 🔹 문제 가능성이 있는 페이지는 지연 로딩
const Analyze = React.lazy(() => import('./components/Analyze'));
const Dashboard = React.lazy(() => import('./components/Dashboard'));

// 🔹 에러 바운더리로 어디서 터지는지 잡자
class RouteErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: any }> {
  constructor(props: any) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: any) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 16 }}>
          <h2 style={{ fontWeight: 700, marginBottom: 8 }}>화면 로딩 중 오류</h2>
          <pre style={{ whiteSpace: 'pre-wrap' }}>
            {String(this.state.error?.message || this.state.error)}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

const ProtectedRoute: React.FC = () => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div>로딩 중...</div>;
  if (!user) return <Navigate to="/auth" state={{ from: location }} replace />;
  return <Outlet />;
};

const MainLayout: React.FC<{
  children: React.ReactNode;
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
}> = ({ children, isSidebarOpen, toggleSidebar }) => (
  <div className="flex h-screen bg-brand-gray-100 relative">
    <Sidebar isOpen={isSidebarOpen} toggleSidebar={toggleSidebar} />
    {!isSidebarOpen && (
      <button
        className="md:hidden absolute top-4 left-4 z-50 text-2xl text-gray-800"
        onClick={toggleSidebar}
      >
        ☰
      </button>
    )}
    <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">{children}</main>
  </div>
);

export default function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  useEffect(() => { fetch(`${import.meta.env.VITE_API_BASE}/ping`).catch(() => {}); }, []);
  const toggleSidebar = () => setIsSidebarOpen(prev => !prev);

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
                  <RouteErrorBoundary>
                    <Suspense fallback={<div>분석 화면 로딩 중...</div>}>
                      <Analyze />
                    </Suspense>
                  </RouteErrorBoundary>
                </MainLayout>
              }
            />
            <Route
              path="/dashboard"
              element={
                <MainLayout isSidebarOpen={isSidebarOpen} toggleSidebar={toggleSidebar}>
                  <RouteErrorBoundary>
                    <Suspense fallback={<div>대시보드 로딩 중...</div>}>
                      <Dashboard />
                    </Suspense>
                  </RouteErrorBoundary>
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