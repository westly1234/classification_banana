import React, { useState, createContext, useContext, useMemo } from 'react';
import type { AuthContextType, User } from '../types';

// 1. 인증 컨텍스트 생성
const AuthContext = createContext<AuthContextType | null>(null);

// 2. 인증 훅 (useAuth) 생성
export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth는 AuthProvider 내에서 사용해야 합니다.');
    }
    return context;
};

// 3. 인증 제공자 (AuthProvider) 컴포넌트
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<User | null>(null);

    const login = (userData: User) => {
        setUser(userData);
        // 실제 앱에서는 여기에 localStorage에 토큰을 저장하는 로직을 추가합니다.
    };

    const logout = () => {
        setUser(null);
        // 실제 앱에서는 여기에서 localStorage의 토큰을 제거합니다.
    };
    
    // user 상태가 변경될 때만 value 객체를 재생성하여 불필요한 리렌더링 방지
    const value = useMemo(() => ({
        user,
        isAuthenticated: !!user,
        login,
        logout,
    }), [user]);

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
