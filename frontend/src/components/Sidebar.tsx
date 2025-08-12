import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { FiX } from 'react-icons/fi'; // 모바일용 닫기 아이콘

const icons = {
  Dashboard: (props: React.SVGProps<SVGSVGElement>) => (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"  />
    </svg>
  ),
  Analyze: (props: React.SVGProps<SVGSVGElement>) => (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 01-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 013.09-3.09L12 5.25l2.846.813a4.5 4.5 0 013.09 3.09L21.75 12l-2.846.813a4.5 4.5 0 01-3.09 3.09L12 18.75l-2.187-2.846zM12 13.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" />
    </svg>
  ),
  User: (props: React.SVGProps<SVGSVGElement>) => (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M17.982 18.725A7.488 7.488 0 0012 15.75a7.488 7.488 0 00-5.982 2.975m11.963 0a9 9 0 10-11.963 0m11.963 0A8.966 8.966 0 0112 21a8.966 8.966 0 01-5.982-2.275M15 9.75a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  Logout: (props: React.SVGProps<SVGSVGElement>) => (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
    </svg>
  ),
};

const NavItem: React.FC<{ to: string; icon: React.ReactNode; children: React.ReactNode; onClick?: () => void }> = ({ to, icon, children, onClick }) => {
  const navLinkClasses = "flex items-center p-3 my-1 rounded-lg text-brand-gray-700 hover:bg-brand-green/20 hover:text-brand-gray-900 transition-colors duration-200";
  const activeClasses = "bg-brand-green/20 text-brand-green-800 font-semibold shadow-sm";

  return (
    <NavLink to={to} onClick={onClick} className={({ isActive }) => `${navLinkClasses} ${isActive ? activeClasses : ''}`}>
      <span className="mr-4">{icon}</span>
      <span className="text-sm">{children}</span>
    </NavLink>
  );
};

export default function Sidebar({ isOpen, toggleSidebar }: { isOpen: boolean; toggleSidebar: () => void }) {
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/auth');
  };

  const commonSidebar = (
    <>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200">
        <div className="flex items-center">
          <img src="https://em-content.zobj.net/source/apple/354/banana_1f34c.png" alt="Banana" className="h-6 w-6" />
          <h1 className="ml-2 text-lg font-bold text-gray-800">바나나-리틱스</h1>
        </div>
        {/* 모바일용 닫기 버튼 */}
        <button className="md:hidden" onClick={toggleSidebar}>
          <FiX size={24} />
        </button>
      </div>

      {/* Nav */}
      <nav className="mt-4 flex-1 px-4">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">메뉴</p>
        <NavItem to="/analyze" icon={<icons.Analyze className="w-6 h-6" />} onClick={toggleSidebar}>바나나 분석</NavItem>
        <NavItem to="/dashboard" icon={<icons.Dashboard className="w-6 h-6" />} onClick={toggleSidebar}>대시보드</NavItem>
      </nav>

      {/* User Info & Logout */}
      <div className="p-4 border-t border-gray-200">
        <div className="flex items-center">
          <icons.User className="w-8 h-8 text-gray-500" />
          <div className="ml-3">
            <p className="text-sm font-semibold text-gray-800">{user?.nickname}</p>
            <p className="text-xs text-gray-500">{user?.email}</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="mt-4 w-full flex items-center p-2 rounded-lg text-gray-700 hover:bg-red-100 hover:text-red-700"
        >
          <icons.Logout className="w-6 h-6 mr-3" />
          <span className="text-sm">로그아웃</span>
        </button>
      </div>
    </>
  );

  return (
    <aside
        className={`
        fixed top-0 left-0 z-50 w-64 h-full
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        bg-white md:bg-transparent
        shadow-lg transform transition-transform
        md:translate-x-0 md:static md:flex md:flex-col
        `}
    >
        {commonSidebar}
    </aside>
    );
}
