// src/services/yoloService.ts
import type { YoloAnalysisResult } from '../types';
import api from '../components/api';

export interface AnalyzeResponse {
  detections: YoloAnalysisResult[];
  avg_confidence: number;
}

/** data URL에서 접두부 제거: png/jpeg/webp 등 + 추가 파라미터도 허용 */
function stripDataUrlPrefix(dataUrl: string) {
  return dataUrl.replace(/^data:image\/[a-zA-Z0-9.+-]+;base64,/, '');
}

/**
 * base64(또는 data URL)를 백엔드로 보내 YOLO 분석
 */
export async function analyzeBananaWithYolo(base64Image: string): Promise<AnalyzeResponse> {
  const clean = stripDataUrlPrefix(base64Image);

  try {
    const { data } = await api.post<AnalyzeResponse>('/analysis/analyze', { image: clean });
    // 방어적 기본값
    return {
      detections: Array.isArray(data?.detections) ? data.detections : [],
      avg_confidence: typeof data?.avg_confidence === 'number' ? data.avg_confidence : 0,
    };
  } catch (err: any) {
    const msg =
      err?.response?.data?.detail ||
      err?.message ||
      '바나나 분석 요청 중 오류가 발생했습니다.';
    throw new Error(msg);
  }
}