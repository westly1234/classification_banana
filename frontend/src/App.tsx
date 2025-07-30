import React from 'react';
import { HashRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Sidebar from './components/Sidebar';
import AuthPage from './components/Auth';
import Dashboard from './components/Dashboard';
import Analyze from './components/Analyze';

// 보호된 라우트 (ProtectedRoute) 컴포넌트
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { isAuthenticated } = useAuth();
    const location = useLocation();

    if (!isAuthenticated) {
        // 로그인되어 있지 않으면 로그인 페이지로 리디렉션
        // 사용자가 원래 가려던 페이지 정보를 state에 담아 전달
        return <Navigate to="/auth" state={{ from: location }} replace />;
    }

    return <>{children}</>;
};

// 메인 레이아웃 컴포넌트
const MainLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <div className="flex h-screen bg-brand-gray-100">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
            {children}
        </main>
    </div>
);

// 메인 앱 컴포넌트
export default function App() {
    return (
        <AuthProvider>
            <HashRouter>
                <Routes>
                    {/* 인증이 필요 없는 라우트 */}
                    <Route path="/auth" element={<AuthPage />} />

                    {/* 인증이 필요한 라우트들을 ProtectedRoute로 감쌉니다. */}
                    <Route path="/" element={<ProtectedRoute><Navigate to="/analyze" replace /></ProtectedRoute>} />
                    <Route path="/analyze" element={<ProtectedRoute><MainLayout><Analyze /></MainLayout></ProtectedRoute>} />
                    <Route path="/dashboard" element={<ProtectedRoute><MainLayout><Dashboard /></MainLayout></ProtectedRoute>} />
                    
                    {/* 일치하는 라우트가 없을 경우 기본 페이지로 리디렉션 */}
                    <Route path="*" element={<Navigate to="/" />} />
                </Routes>
            </HashRouter>
        </AuthProvider>
    );
}
