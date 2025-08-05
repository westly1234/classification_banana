import React, { useState } from 'react';
import Sidebar from './Sidebar';

interface MainLayoutProps {
  children: React.ReactNode;
}

const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const toggleSidebar = () => setSidebarOpen(prev => !prev);

  return (
    <div className="flex flex-col md:flex-row h-screen bg-brand-gray-100 relative">

      {/* ✅ 모바일 햄버거 버튼: 왼쪽 상단 고정, 사이드바 열릴 때 숨김 */}
      {!isSidebarOpen && (
        <button
          onClick={toggleSidebar}
          className="md:hidden absolute top-4 left-4 z-50 text-2xl text-gray-800"
        >
          ☰
        </button>
      )}

      {/* ✅ Sidebar (모바일 시 슬라이드, 데스크탑은 항상 보임) */}
      <Sidebar isOpen={isSidebarOpen} toggleSidebar={toggleSidebar} />

      {/* ✅ 메인 콘텐츠 */}
      <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
        {/* ✅ 모바일에서만 가운데 정렬 */}
        <h1 className="text-2xl font-bold mb-6 text-center md:text-left">대시보드</h1>
        {children}
      </main>
    </div>
  );
};

export default MainLayout;
