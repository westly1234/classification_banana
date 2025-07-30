// 사용자 정보
export interface User {
  name: string;
  email: string;
}

// 인증 컨텍스트 타입
export interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  login: (user: User) => void;
  logout: () => void;
}

// YOLO 백엔드로부터 받는 분석 결과 타입
export interface YoloAnalysisResult {
  ripeness: string;
  confidence: number;
  boundingBox: {
    x: number;      // 상대 좌표 (0-1)
    y: number;      // 상대 좌표 (0-1)
    width: number;  // 상대 크기 (0-1)
    height: number; // 상대 크기 (0-1)
  };
}

// Gemini API로부터 받는 분석 결과 타입
export interface GeminiAnalysisResult {
    ripeness: string;
    condition_description: string;
    best_use: string;
    fun_fact: string;
}


// 분석 이력에 사용될 타입 (대시보드 등)
export interface AnalysisHistory {
    id: string;
    date: string;
    imageUrl: string;
    details: YoloAnalysisResult;
}