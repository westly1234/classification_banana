
import React, { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import type { YoloAnalysisResult } from '../types';
import { analyzeBananaWithYolo } from '../services/yoloService';

// 분석 중 표시될 로딩 메시지 목록
const loadingSteps = [
    "분석 초기화 중...",
    "이미지 전처리 중...",
    "YOLO 모델 탐지 실행 중...",
    "분류 대기 중...",
    "결과 최종 확인 중..."
];

// File 객체를 Base64 문자열로 변환하는 헬퍼 함수
const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve((reader.result as string).split(',')[1]); // 'data:...' 부분을 제거
        reader.onerror = error => reject(error);
    });
};

export default function Analyze() {
    const [file, setFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [loadingText, setLoadingText] = useState(loadingSteps[0]);
    const [result, setResult] = useState<YoloAnalysisResult | null>(null);
    const [error, setError] = useState<string | null>(null);

    // Dropzone: 파일이 드롭되었을 때 호출되는 콜백 함수
    const onDrop = useCallback((acceptedFiles: File[]) => {
        if (acceptedFiles && acceptedFiles.length > 0) {
            const selectedFile = acceptedFiles[0];
            setFile(selectedFile);
            setPreview(URL.createObjectURL(selectedFile));
            setResult(null); // 이전 결과 초기화
            setError(null);  // 이전 에러 초기화
        }
    }, []);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: { 'image/*': ['.jpeg', '.png', '.jpg', '.webp'] },
        multiple: false
    });

    // '분석하기' 버튼 클릭 시 실행되는 함수
    const handleAnalyze = async () => {
        if (!file) return;

        setIsLoading(true);
        setResult(null);
        setError(null);

        // 로딩 메시지를 주기적으로 변경
        let step = 0;
        const interval = setInterval(() => {
            step = (step + 1) % loadingSteps.length;
            setLoadingText(loadingSteps[step]);
        }, 1500);

        try {
            const base64Image = await fileToBase64(file);
            const analysisResult = await analyzeBananaWithYolo(base64Image);
            setResult(analysisResult);
        } catch (err: any) {
            console.error(err);
            setError(err.message || '바나나 분석에 실패했습니다. 백엔드 연결을 확인하고 다시 시도해주세요.');
        } finally {
            clearInterval(interval);
            setIsLoading(false);
        }
    };
    
    // 분석 결과로부터 바운딩 박스 스타일 계산
    const boundingBoxStyle = result ? {
        top: `${result.boundingBox.y * 100}%`,
        left: `${result.boundingBox.x * 100}%`,
        width: `${result.boundingBox.width * 100}%`,
        height: `${result.boundingBox.height * 100}%`,
    } : {};

    return (
        <div className="max-w-6xl mx-auto">
            <div className="text-center mb-10">
                <h1 className="text-4xl font-extrabold text-brand-gray-900">바나나 상태 분류기</h1>
                <p className="mt-2 text-lg text-brand-gray-600">바나나 사진을 업로드하여 즉시 YOLO 모델 분석 결과를 받아보세요!</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
                {/* 왼쪽: 업로드 및 미리보기 */}
                <div className="bg-white p-8 rounded-2xl shadow-lg">
                    <div
                        {...getRootProps()}
                        className={`border-4 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors duration-300 ${isDragActive ? 'border-banana-yellow bg-yellow-50' : 'border-brand-gray-300 hover:border-banana-yellow'}`}
                    >
                        <input {...getInputProps()} />
                        <div className="flex flex-col items-center">
                            <svg className="w-16 h-16 text-brand-gray-400 mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l-3.75 3.75M12 9.75l3.75 3.75M3 17.25V6.75A2.25 2.25 0 015.25 4.5h13.5A2.25 2.25 0 0121 6.75v10.5A2.25 2.25 0 0118.75 19.5H5.25A2.25 2.25 0 013 17.25z" />
                            </svg>
                            {isDragActive ?
                                <p className="text-lg font-semibold text-banana-yellow">여기에 바나나를 놓으세요!</p> :
                                <p className="text-lg text-brand-gray-600">이미지를 드래그 앤 드롭하거나 클릭해서 선택하세요</p>
                            }
                            <p className="text-sm text-brand-gray-400 mt-1">PNG, JPG, WEBP 최대 10MB</p>
                        </div>
                    </div>
                    {preview && (
                        <div className="mt-6">
                            <h3 className="font-bold text-lg mb-2">이미지 미리보기:</h3>
                            <div className="relative">
                                <img src={preview} alt="바나나 미리보기" className="w-full h-auto rounded-lg shadow-md" />
                                {result && (
                                     <div 
                                         className="absolute border-4 border-banana-yellow rounded-md transition-all duration-500 ease-in-out" 
                                         style={boundingBoxStyle}
                                     >
                                        <span className="absolute -top-7 left-0 bg-banana-yellow text-black text-xs font-bold px-2 py-1 rounded">
                                            {result.ripeness} ({(result.confidence * 100).toFixed(1)}%)
                                        </span>
                                     </div>
                                )}
                            </div>
                            <button onClick={handleAnalyze} disabled={isLoading || !file} className="mt-6 w-full bg-brand-green text-white font-bold py-3 px-4 rounded-lg hover:bg-green-600 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:bg-brand-gray-400 disabled:cursor-not-allowed transition-all duration-300 text-lg flex items-center justify-center">
                                {isLoading ? (
                                    <>
                                        <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        분석 중...
                                    </>
                                ) : '지금 분석하기'}
                            </button>
                        </div>
                    )}
                </div>

                {/* 오른쪽: 결과 표시 */}
                <div className="bg-white p-8 rounded-2xl shadow-lg min-h-[300px] flex flex-col justify-center">
                    {isLoading && (
                        <div className="text-center">
                            <div className="w-24 h-24 mx-auto animate-bounce">
                                <img src="https://em-content.zobj.net/source/apple/354/banana_1f34c.png" alt="로딩 중인 바나나" />
                            </div>
                            <p className="mt-4 text-xl font-semibold text-brand-gray-800">{loadingText}</p>
                        </div>
                    )}
                    {error && <p className="text-center text-red-500 font-bold">{error}</p>}
                    {result && (
                        <div className="space-y-4 animate-fade-in">
                             <h2 className="text-3xl font-bold text-brand-gray-900 border-b-4 border-banana-yellow pb-2">분석 완료!</h2>
                             <div>
                                 <h3 className="text-sm uppercase font-bold text-brand-gray-500">분류</h3>
                                 <p className="text-2xl font-semibold text-banana-green">{result.ripeness}</p>
                             </div>
                              <div>
                                 <h3 className="text-sm uppercase font-bold text-brand-gray-500">신뢰도 점수</h3>
                                 <p className="text-2xl font-semibold text-brand-green">{(result.confidence * 100).toFixed(1)}%</p>
                             </div>
                             <div className="bg-green-50 border-l-4 border-brand-green text-green-800 p-4 rounded-r-lg">
                                 <h3 className="text-sm uppercase font-bold text-green-900">다음 단계</h3>
                                 <p className="mt-1">왼쪽의 경계 상자는 탐지된 바나나를 보여줍니다. 이제 실제 YOLO 모델을 백엔드에 통합할 수 있습니다.</p>
                             </div>
                        </div>
                    )}
                    {!isLoading && !result && !error && (
                        <div className="text-center text-brand-gray-500">
                             <svg className="w-16 h-16 mx-auto mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" /></svg>
                             <p className="text-lg">YOLO 분석 결과가 여기에 표시됩니다.</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
