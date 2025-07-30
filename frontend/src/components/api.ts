// src/api.ts

import axios from 'axios';

const API_BASE = "http://localhost:8000";

const api = axios.create({
    baseURL: API_BASE,
});

// 요청 인터셉터: 모든 요청에 토큰을 자동으로 추가
api.interceptors.request.use(
    config => {
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        return config;
    },
    error => {
        return Promise.reject(error);
    }
);

// 응답 인터셉터: 401 에러 발생 시 자동으로 로그아웃 처리
api.interceptors.response.use(
    response => {
        return response;
    },
    error => {
        if (error.response && error.response.status === 401) {
            // 토큰 관련 에러일 경우, 저장된 정보 삭제 후 로그인 페이지로 이동
            localStorage.removeItem('access_token');
            localStorage.removeItem('user');
            alert("세션이 만료되었습니다. 다시 로그인해주세요.");
            // 현재 위치를 강제로 변경하여 AuthContext가 리렌더링되도록 함
            window.location.href = '/auth'; 
        }
        return Promise.reject(error);
    }
);

export default api;