
import type { YoloAnalysisResult } from '../types';

// 실제 FastAPI 백엔드 주소입니다.
// 로컬에서 FastAPI 서버를 실행하는 경우 보통 이 주소를 사용합니다.
const API_BASE = import.meta.env.VITE_API_BASE;
export const API_ENDPOINT = `${API_BASE}/analyze`;

/**
 * base64로 인코딩된 이미지를 YOLO 백엔드 서버로 보내 분석을 요청하는 함수
 * @param base64Image 분석할 이미지의 base64 인코딩된 문자열
 * @returns {Promise<YoloAnalysisResult>} 서버로부터 받은 분석 결과
 */
export async function analyzeBananaWithYolo(base64Image: string): Promise<YoloAnalysisResult> {
    console.log(`실제 API 호출을 ${API_ENDPOINT}로 보냅니다.`);

    try {
        const response = await fetch(API_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            // 이미지를 base64 문자열 형태로 body에 담아 보냅니다.
            body: JSON.stringify({ image: base64Image })
        });

        // 응답이 성공적이지 않은 경우 에러를 던집니다.
        if (!response.ok) {
            // 서버에서 보낸 에러 메시지를 포함하여 좀 더 구체적인 에러를 생성합니다.
            const errorData = await response.json().catch(() => ({ detail: "서버로부터 JSON 형식의 에러 메시지를 받지 못했습니다." }));
            throw new Error(`네트워크 응답이 올바르지 않습니다: ${response.status} ${response.statusText}. 서버 메시지: ${errorData.detail}`);
        }
        
        // 성공적인 응답의 JSON을 파싱하여 반환합니다.
        const result: YoloAnalysisResult = await response.json();
        return result;

    } catch (error) {
        console.error("YOLO 백엔드 API 호출 중 오류 발생:", error);
        
        // 사용자에게 보여줄 좀 더 친절한 에러 메시지를 생성합니다.
        if (error instanceof TypeError) { // 네트워크 연결 실패 등
            throw new Error("바나나 분석 서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지, 주소가 올바른지 확인해주세요.");
        }
        
        // 그 외의 에러는 그대로 다시 던집니다.
        throw error;
    }
}
