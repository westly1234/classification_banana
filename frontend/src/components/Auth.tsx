import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE;// 백엔드 주소

export default function AuthPage() {
    const [isLoginView, setIsLoginView] = useState(true);
    const [nickname, setNickname] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();
    const { login } = useAuth();

    const from = location.state?.from?.pathname || "/analyze";

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            if (isLoginView) {
                const params = new URLSearchParams();
                params.append('username', email);
                params.append('password', password);

                const res = await axios.post(`${API_BASE}/login`, params);

                const token = res.data.access_token;
                localStorage.setItem("access_token", token); // 토큰 저장을 먼저 실행

                let decodedNickname = null;
                try {
                    // 에러 발생 가능성이 높은 코드를 별도의 try-catch로 감쌉니다.
                    const decodedPayload = JSON.parse(atob(token.split('.')[1]));
                    decodedNickname = decodedPayload.nickname;
                } catch (e) {
                    console.error("JWT 토큰 디코딩 중 에러 발생:", e);
                    // 여기서 에러가 나도 전체 로직이 멈추지 않고 계속 진행됩니다.
                }

                // login 컨텍스트 함수 호출
                login({ name: decodedNickname || email.split("@")[0], email });

                // 페이지 이동 함수 호출 (이제는 이 코드가 반드시 실행됩니다)
                navigate(from, { replace: true });
            } else {
                // 회원가입 로직은 JSON 형식이므로 그대로 둡니다.
                // (main.py의 signup 함수가 Pydantic 모델 UserCreate를 사용하므로 JSON을 잘 처리합니다.)
                if (password !== confirmPassword) {
                    setError("비밀번호가 일치하지 않습니다.");
                    setLoading(false);
                    return;
                }

                await axios.post(`${API_BASE}/signup`, {
                    nickname, // 백엔드 UserCreate 모델은 'username'이 아니라 'nickname'을 기대합니다. 이 부분도 확인이 필요합니다.
                    email,
                    password,
                    password_confirm: confirmPassword
                });

                alert("이메일 인증 링크가 발송되었습니다. 메일을 확인해주세요.");
                setIsLoginView(true);
            }
        } catch (err: any) {
            console.error("❌ 요청 실패:", err.response?.data || err);
            setError(err.response?.data?.detail || "요청 처리 중 오류가 발생했습니다.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex items-center justify-center min-h-screen bg-brand-gray-50">
            <div className="w-full max-w-md p-8 space-y-8 bg-white rounded-2xl shadow-xl">
                <div className="text-center">
                    <img 
                        src="https://em-content.zobj.net/source/apple/354/banana_1f34c.png" 
                        alt="Banana" 
                        className="w-16 h-16 mx-auto" 
                    />
                    <h2 className="mt-6 text-3xl font-bold text-gray-900">
                        {isLoginView ? '다시 오신 것을 환영합니다!' : '계정 만들기'}
                    </h2>
                    <p className="mt-2 text-sm text-gray-600">
                        바나나-리틱스 대시보드에 접속하세요
                    </p>
                </div>

                <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
                    {!isLoginView && (
                        <input
                            type="text"
                            placeholder="닉네임"
                            value={nickname}
                            onChange={(e) => setNickname(e.target.value)}
                            required
                            className="w-full px-5 py-3 border rounded-md focus:outline-none focus:ring-2 focus:ring-banana-yellow"
                        />
                    )}
                    <input
                        type="email"
                        placeholder="이메일 주소"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        className="w-full px-5 py-3 border rounded-md focus:outline-none focus:ring-2 focus:ring-banana-yellow"
                    />
                    <input
                        type="password"
                        placeholder="비밀번호"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        className="w-full px-5 py-3 border rounded-md focus:outline-none focus:ring-2 focus:ring-banana-yellow"
                    />
                    {!isLoginView && (
                        <input
                            type="password"
                            placeholder="비밀번호 확인"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            required
                            className="w-full px-5 py-3 border rounded-md focus:outline-none focus:ring-2 focus:ring-banana-yellow"
                        />
                    )}
                    {error && <p className="text-red-500 text-sm">{error}</p>}
                    <button 
                        type="submit" 
                        disabled={loading}
                        className={`w-full py-3 text-gray-800 bg-banana-yellow rounded-md hover:bg-yellow-400 transition-all duration-300 ${loading ? "opacity-50 cursor-not-allowed" : ""}`}
                    >
                        {loading ? '처리 중...' : (isLoginView ? '로그인' : '회원가입')}
                    </button>
                </form>

                <p className="text-sm text-center text-gray-600">
                    {isLoginView ? "계정이 없으신가요?" : '이미 계정이 있으신가요?'}
                    <button 
                        onClick={() => setIsLoginView(!isLoginView)} 
                        className="ml-1 font-medium text-banana-green hover:text-green-600"
                    >
                        {isLoginView ? '회원가입' : '로그인'}
                    </button>
                </p>
            </div>
        </div>
    );
}