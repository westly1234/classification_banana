//src/services/yoloService.ts
import type { YoloAnalysisResult } from '../types';
import api from '../components/api';

// 서버 응답 형태에 맞춘 타입 (백엔드: { detections: [...], avg_confidence: number })
export interface AnalyzeResponse {
  detections: YoloAnalysisResult[];
  avg_confidence: number;
}

/**
 * base64(또는 data URL)를 백엔드로 보내 YOLO 분석
 */
export async function analyzeBananaWithYolo(base64Image: string): Promise<AnalyzeResponse> {
  // "data:image/png;base64,..." 같은 접두어 제거 → 순수 base64만 전송
  const clean = base64Image.replace(/^data:image\/\w+;base64,/, '');

  try {
    const { data } = await api.post<AnalyzeResponse>('/analysis/analyze', { image: clean });
    return data;
  } catch (err: any) {
    const msg =
      err?.response?.data?.detail ||
      err?.message ||
      '바나나 분석 요청 중 오류가 발생했습니다.';
    throw new Error(msg);
  }
}
