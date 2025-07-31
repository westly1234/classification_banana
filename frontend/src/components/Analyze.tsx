import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import type { YoloAnalysisResult, ImageAnalysisResultPayload } from '../types';
import api from './api';

interface AnalysisState {
    id: string;
    file: File;
    previewUrl: string;
    result: YoloAnalysisResult[] | null; // 단일 객체가 아닌 배열
    error: string | null;
    isLoading: boolean;
    isSelected: boolean;
    avg_confidence?: number; 
}

type StorableAnalysisState = Omit<AnalysisState, 'file'> & { fileName: string, fileType: string };

const API_BASE = "http://192.168.0.48:8000";

const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
            const result = reader.result as string;
            if (!result || !result.includes(",")) {
                reject("Base64 변환 실패");
                return;
            }
            resolve(result.split(",")[1]);
        };
        reader.onerror = error => reject(error);
    });
};

export default function Analyze() {
    const [analysisStates, setAnalysisStates] = useState<AnalysisState[]>([]);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const navigate = useNavigate();
    const [videoUrl, setVideoUrl] = useState<string | null>(null);
    const [taskStatus, setTaskStatus] = useState<string | null>(null);

    useEffect(() => {
        const savedStatesJSON = sessionStorage.getItem('analysisStates');
        const savedVideoUrl = sessionStorage.getItem('lastVideoUrl');
        
        if (savedStatesJSON) {
            // File 객체는 복원할 수 없으므로, previewUrl만 사용해 상태를 재구성합니다.
            // 이렇게 하면 새로고침해도 이미지는 보이지만, 재분석은 불가능합니다. (의도된 동작)
            const savedStates: StorableAnalysisState[] = JSON.parse(savedStatesJSON);
            const restoredStates: AnalysisState[] = savedStates.map(s => ({
                ...s,
                file: new File([], s.fileName, { type: s.fileType }), // 빈 File 객체로 복원
                previewUrl: s.previewUrl 
            }));
            setAnalysisStates(restoredStates);
        }
        if (savedVideoUrl) {
            setVideoUrl(savedVideoUrl);
            setTaskStatus('이전 동영상 분석 결과를 불러왔습니다.');
        }
    }, []);

    // 상태가 변경될 때마다 sessionStorage에 저장
    useEffect(() => {
        if (analysisStates.length > 0) {
            // File 객체를 제외하고 저장 가능한 형태로 변환
            const storableStates: StorableAnalysisState[] = analysisStates.map(({ file, ...rest }) => ({
                ...rest,
                fileName: file.name,
                fileType: file.type,
            }));
            sessionStorage.setItem('analysisStates', JSON.stringify(storableStates));
        } else {
            sessionStorage.removeItem('analysisStates');
        }
    }, [analysisStates]);

    const fileToBase64Url = (file: File): Promise<string> => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => resolve(reader.result as string);
            reader.onerror = reject;
        });
    };

    const onDrop = useCallback(async (acceptedFiles: File[]) => {
        const validFiles = acceptedFiles.filter(file => file.size > 0 && file.type.startsWith("image/"));
        if (validFiles.length === 0) {
            alert("유효한 이미지 파일이 없습니다.");
            return;
        }

        const newStates: AnalysisState[] = await Promise.all(
            validFiles.map(async file => ({
                id: `${file.name}-${file.lastModified}-${Math.random()}`,
                file,
                previewUrl: await fileToBase64Url(file),
                result: null,
                error: null,
                isLoading: false,
                isSelected: false,
                avg_confidence: undefined,  // ✅ 평균값 초기화
            }))
        );

        setVideoUrl(null);
        setTaskStatus(null);
        localStorage.removeItem("lastVideoUrl");
        setAnalysisStates(newStates);
    }, []);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: { 'image/*': ['.jpeg', '.png', '.jpg', '.webp'] }, multiple: true });

    const handleAnalyze = async () => {
        // [수정] 파일 크기가 0보다 큰, '진짜' 파일만 분석 대상으로 필터링합니다.
        const statesToAnalyze = analysisStates.filter(
            s => s.file && s.file.size > 0 && !s.result && !s.error
        );

        if (statesToAnalyze.length === 0) {
            alert("분석할 새로운 이미지가 없습니다. 페이지를 새로고침 하셨다면, 이미지를 다시 업로드해주세요.");
            return;
        }

        setIsAnalyzing(true);
        try {
            // [수정] 분석할 이미지 개수에 따라 다른 함수를 호출하고, '진짜' 파일 목록을 넘겨줍니다.
            if (statesToAnalyze.length === 1) {
                await analyzeSingleImage(statesToAnalyze[0]);
            } else {
                await analyzeMultipleImagesAsVideo(statesToAnalyze);
            }
        } catch (error) {
            console.error("분석 프로세스 중 처리되지 않은 에러 발생:", error);
        } finally {
            setIsAnalyzing(false);
        }
    };

    const analyzeSingleImage = async (targetState: AnalysisState) => {
        const targetId = targetState.id;

        // 1. 분석 시작을 알리는 로딩 상태로 변경
        setAnalysisStates(prev => prev.map(s =>
            s.id === targetId ? { ...s, isLoading: true, error: null } : s
        ));

        try {
            const base64Image = await fileToBase64(targetState.file);

            // [핵심 수정] 백엔드가 보내주는 { detections: [...], ... } 객체 타입을 명시합니다.
            const res = await api.post<ImageAnalysisResultPayload>(`/analyze`, { image: base64Image });

            // [핵심 수정] 이제 res.data는 배열이 아닌 객체이므로, 바로 구조를 분해해서 사용합니다.
            const { detections, avg_confidence } = res.data;

            // [핵심 수정] 백엔드의 'ripeness'를 프론트엔드의 'label'로 매핑해줍니다.
            const formattedDetections = detections.map(d => ({
                ...d,
                label: d.ripeness // 데이터 이름 통일
            }));

            // 3. 분석 결과를 상태에 업데이트
            setAnalysisStates(prev => prev.map(s =>
                s.id === targetId
                    ? {
                        ...s,
                        result: formattedDetections,
                        avg_confidence: avg_confidence ?? 0, // 백엔드에서 받은 평균값 사용
                        isLoading: false
                    }
                    : s
            ));

        } catch (err: any) {
            const msg = err.response?.data?.detail || "분석 실패";
            setAnalysisStates(prev => prev.map(s =>
                s.id === targetId ? { ...s, error: msg, isLoading: false } : s
            ));
        }
    };

    const analyzeMultipleImagesAsVideo = (statesToAnalyze: AnalysisState[]): Promise<void> => {
        return new Promise(async (resolve, reject) => {
            setTaskStatus("이미지 분석 및 동영상 생성 요청 중...");

            // 분석을 시작할 이미지들의 ID를 저장해둡니다.
            const idsToAnalyze = new Set(statesToAnalyze.map(s => s.id));

            // 해당 이미지들의 로딩 상태를 true로 변경합니다.
            setAnalysisStates(prev => prev.map(s =>
                idsToAnalyze.has(s.id) ? { ...s, isLoading: true, error: null } : s
            ));

            try {
                const formData = new FormData();
                statesToAnalyze.forEach((state) => {
                    formData.append("files", state.file);
                });

                // [핵심 로직 1] 백엔드에 이미지들을 전송하고, 즉시 개별 분석 결과를 받습니다.
                const res = await api.post<{ task_id: string; results: ImageAnalysisResultPayload[] }>(
                    `/analyze_video`,
                    formData,
                    {
                        headers: { "Content-Type": "multipart/form-data" },
                        maxContentLength: Infinity,
                        maxBodyLength: Infinity,
                    }
                );

                const { task_id, results } = res.data;

                // [핵심 로직 2] 백엔드에서 받은 개별 분석 결과를 즉시 화면에 업데이트합니다.
                const resultsMap = new Map(results.map(r => [r.filename, r]));
                setAnalysisStates(prev => prev.map(state => {
                    const match = resultsMap.get(state.file.name);
                    if (match) {
                        // YoloAnalysisResult 타입과 맞추기 위해 'ripeness'를 'label'로 변경
                        const formattedDetections = match.detections.map(d => ({
                            ...d,
                            label: d.ripeness 
                        }));

                        return {
                            ...state,
                            result: formattedDetections,
                            avg_confidence: match.avg_confidence ?? 0,
                            isLoading: false, // 개별 분석 끝났으므로 로딩 해제
                            error: null,
                        };
                    }
                    return state;
                }));

                // [핵심 로직 3] 이제부터는 '동영상 생성' 상태만 주기적으로 확인합니다.
                setTaskStatus("동영상 생성 중... (최대 몇 분 소요될 수 있습니다)");

                const intervalId = setInterval(async () => {
                    try {
                        const statusRes = await api.get(`/tasks/${task_id}/status`);
                        const { status, result } = statusRes.data;

                        if (status === 'SUCCESS' || status === 'FAILURE') {
                            clearInterval(intervalId);
                            if (status === 'SUCCESS') {
                                const finalUrl = `${API_BASE}${result}`;
                                setVideoUrl(finalUrl);
                                sessionStorage.setItem('lastVideoUrl', finalUrl);
                                setTaskStatus("동영상 생성 완료!");
                                resolve(); // 성공
                            } else {
                                // 동영상 생성 실패 시 메시지만 업데이트
                                setTaskStatus(`오류: 동영상 생성 실패 (${result})`);
                                reject(new Error(result)); // 실패
                            }
                        }
                    } catch (pollError) {
                        clearInterval(intervalId);
                        setTaskStatus("동영상 상태 확인 중 오류 발생");
                        reject(pollError);
                    }
                }, 5000);

            } catch (requestError: any) {
                const errorMsg = requestError.response?.data?.detail || "분석 요청 실패";
                setTaskStatus(errorMsg);
                // 요청 자체에 실패했으므로 모든 로딩 상태를 해제합니다.
                setAnalysisStates(prev => prev.map(s =>
                    idsToAnalyze.has(s.id) ? { ...s, isLoading: false, error: errorMsg } : s
                ));
                reject(requestError);
            }
        });
    };

    const handleToggleSelect = (id: string) => setAnalysisStates(prev => prev.map(s => (s.id === id ? { ...s, isSelected: !s.isSelected } : s)));
    const handleDeleteSelected = () => setAnalysisStates(prev => prev.filter(s => !s.isSelected));
    const handleClearAll = () => {
        setAnalysisStates([]); setVideoUrl(null); setTaskStatus(null);
        sessionStorage.removeItem('analysisStates'); 
        sessionStorage.removeItem('lastVideoUrl');
    };
    const hasSelectedItems = analysisStates.some(state => state.isSelected);

    return (
        <div className="max-w-7xl mx-auto p-4 md:p-8">
            <div className="text-center mb-10"><h1 className="text-4xl font-extrabold text-brand-gray-900">바나나 상태 분류기</h1><p className="mt-2 text-lg text-brand-gray-600">한 장의 사진은 개별 분석, 여러 장은 동영상으로 분석됩니다.</p></div>
            <div {...getRootProps()} className={`bg-white p-6 md:p-8 rounded-2xl shadow-lg border-4 border-dashed cursor-pointer transition-colors duration-300 mb-8 ${isDragActive ? 'border-yellow-400 bg-yellow-50' : 'border-gray-300 hover:border-yellow-400'}`}>
                <input {...getInputProps()} /><div className="flex flex-col items-center justify-center text-center"><svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg><p className="mt-4 text-lg text-gray-600">이미지들을 드래그 앤 드롭하거나 클릭해서 선택하세요</p><p className="text-sm text-gray-400 mt-1">PNG, JPG, WEBP 최대 10MB</p></div>
            </div>
            {analysisStates.length > 0 && (<div><div className="flex justify-between items-center mb-6"><h2 className="text-2xl font-bold">분석 대상 ({analysisStates.length}개)</h2><div className="flex gap-4"><button onClick={handleDeleteSelected} disabled={isAnalyzing || !hasSelectedItems} className="px-6 py-2 bg-gray-300 text-gray-800 font-semibold rounded-lg hover:bg-gray-400 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed">선택 삭제</button><button onClick={handleClearAll} disabled={isAnalyzing} className="px-6 py-2 bg-red-500 text-white font-semibold rounded-lg hover:bg-red-600 disabled:bg-gray-400">전체 삭제</button><button onClick={handleAnalyze} disabled={isAnalyzing} className="px-6 py-2 bg-yellow-400 text-gray-900 font-bold rounded-lg hover:bg-yellow-500 disabled:bg-gray-400">{isAnalyzing ? '분석 중...' : '분석하기'}</button></div></div>
            {videoUrl ? (
                <div className="mt-6 bg-white p-4 rounded-lg shadow-lg">
                    <h3 className="text-center mb-4 text-xl font-semibold text-blue-800">{taskStatus}</h3>
                    <video 
                        key={videoUrl} 
                        controls 
                        width="100%" 
                        height="auto" 
                        style={{ maxHeight: '500px' }}
                    >
                        <source src={`${videoUrl}?t=${Date.now()}`} type="video/mp4" />
                        브라우저에서 동영상을 재생할 수 없습니다.
                    </video>
                </div>
            ) : (
                <div>
                    {taskStatus && (
                        <div className="text-center my-4 p-4 bg-blue-100 text-blue-800 rounded-lg font-semibold">
                            {taskStatus}
                        </div>
                    )}
                </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                {analysisStates.map((state) => (
                    <div key={state.id} onClick={() => !isAnalyzing && handleToggleSelect(state.id)} className={`relative rounded-lg overflow-visible cursor-pointer transition-all w-full shadow-md ${state.isSelected ? 'ring-4 ring-blue-500 ring-offset-2' : ''}`} style={{ aspectRatio: '1 / 1' }}>
                        <img src={state.previewUrl} alt={`분석 이미지`} className="w-full h-full object-cover" />
                        {state.isLoading && <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white"></div></div>}
                        {state.error && <div className="absolute inset-0 flex items-center justify-center p-2 text-center text-white font-semibold bg-red-800 bg-opacity-80">{state.error}</div>}

                        {state.result && state.result.length > 0 && state.result.map((res, index) => (
                            <React.Fragment key={index}>
                                {/* 바운딩 박스 */}
                                <div
                                    className="absolute border-4 border-yellow-400 rounded-md"
                                    style={{
                                        top: `${res.boundingBox.y * 100}%`,
                                        left: `${res.boundingBox.x * 100}%`,
                                        width: `${res.boundingBox.width * 100}%`,
                                        height: `${res.boundingBox.height * 100}%`
                                    }}
                                ></div>

                                {/* 라벨 텍스트 */}
                                <div
                                    className="absolute bg-black bg-opacity-70 text-yellow-300 text-xs font-semibold px-2 py-1 rounded"
                                    style={{
                                        top: `${Math.max(0, res.boundingBox.y * 100 - 5)}%`,
                                        left: `${res.boundingBox.x * 100}%`,
                                    }}
                                >
                                    {`${res.ripeness} (${(res.confidence * 100).toFixed(1)}%)`}
                                </div>
                            </React.Fragment>
                        ))}
                        {state.avg_confidence !== undefined && (
                            <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-70 text-yellow-300 text-sm font-semibold px-2 py-1 rounded-t">
                                평균 정확도: {(state.avg_confidence * 100).toFixed(1)}% 
                            </div>
                        )}
                        {state.result && state.result.length === 0 && <div className="absolute inset-0 flex items-center justify-center p-2 text-center text-white font-semibold bg-gray-600 bg-opacity-80">바나나를 찾지 못했습니다.</div>}
                    </div>
                ))}
            </div>
        </div>)}
    </div>)}
        
    