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
  label: string;                // YOLO 감지 클래스명 (ex: "완숙", "과숙")
  confidence: number;           // 신뢰도 (0~1)
  boundingBox: {
      x: number;      // 상대 좌표 (0-1)
      y: number;      // 상대 좌표 (0-1)
      width: number;  // 상대 크기 (0-1)
      height: number; // 상대 크기 (0-1)
  };
}

// 분석 이력에 사용될 타입 (대시보드 등)
export interface AnalysisHistory {
    id: string;
    date: string;
    imageUrl: string;
    details: YoloAnalysisResult;
}