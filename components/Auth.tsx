import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../App';

export default function AuthPage() {
    const [isLoginView, setIsLoginView] = useState(true);
    const navigate = useNavigate();
    const { login } = useAuth();

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        // 로그인/회원가입 성공을 시뮬레이션합니다.
        login({ name: '바나나 팬', email: 'fan@banana.com' });
        navigate('/analyze');
    };

    return (
        <div className="flex items-center justify-center min-h-screen bg-brand-gray-50">
            <div className="w-full max-w-md p-8 space-y-8 bg-white rounded-2xl shadow-xl">
                <div className="text-center">
                    <img src="https://em-content.zobj.net/source/apple/354/banana_1f34c.png" alt="Banana" className="w-16 h-16 mx-auto" />
                    <h2 className="mt-6 text-3xl font-bold text-gray-900">
                        {isLoginView ? '다시 오신 것을 환영합니다!' : '계정 만들기'}
                    </h2>
                    <p className="mt-2 text-sm text-gray-600">
                        바나나-리틱스 대시보드에 접속하세요
                    </p>
                </div>
                <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
                    <input type="hidden" name="remember" value="true" />
                    <div className="relative">
                       {!isLoginView && (
                         <div className="mb-4">
                             <label htmlFor="name" className="sr-only">이름</label>
                             <input
                                 id="name"
                                 name="name"
                                 type="text"
                                 required
                                 className="w-full px-5 py-3 text-gray-900 placeholder-gray-500 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-banana-yellow focus:border-transparent"
                                 placeholder="이름"
                             />
                         </div>
                       )}
                        <div className="mb-4">
                            <label htmlFor="email-address" className="sr-only">이메일 주소</label>
                            <input
                                id="email-address"
                                name="email"
                                type="email"
                                autoComplete="email"
                                required
                                className="w-full px-5 py-3 text-gray-900 placeholder-gray-500 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-banana-yellow focus:border-transparent"
                                placeholder="이메일 주소"
                            />
                        </div>
                        <div>
                            <label htmlFor="password" className="sr-only">비밀번호</label>
                            <input
                                id="password"
                                name="password"
                                type="password"
                                autoComplete="current-password"
                                required
                                className="w-full px-5 py-3 text-gray-900 placeholder-gray-500 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-banana-yellow focus:border-transparent"
                                placeholder="비밀번호"
                            />
                        </div>
                    </div>

                    <div>
                        <button
                            type="submit"
                            className="w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-md text-gray-800 bg-banana-yellow hover:bg-yellow-400 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-banana-yellow transition-all duration-300"
                        >
                            {isLoginView ? '로그인' : '회원가입'}
                        </button>
                    </div>
                </form>
                <p className="text-sm text-center text-gray-600">
                    {isLoginView ? "계정이 없으신가요?" : '이미 계정이 있으신가요?'}
                    <button onClick={() => setIsLoginView(!isLoginView)} className="ml-1 font-medium text-banana-green hover:text-green-600">
                        {isLoginView ? '회원가입' : '로그인'}
                    </button>
                </p>
            </div>
        </div>
    );
}