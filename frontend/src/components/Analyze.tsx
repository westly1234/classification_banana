import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import type { YoloAnalysisResult } from '../types';
import api from './api';

interface AnalysisState {
    id: string;
    file: File;
    previewUrl: string;
    result: YoloAnalysisResult[] | null; // 단일 객체가 아닌 배열
    error: string | null;
    isLoading: boolean;
    isSelected: boolean;
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
        const newStates: AnalysisState[] = await Promise.all(
            acceptedFiles.map(async file => ({
                id: `${file.name}-${file.lastModified}-${Math.random()}`,
                file,
                previewUrl: await fileToBase64Url(file),
                result: null, error: null, isLoading: false, isSelected: false,
            }))
        );
        setVideoUrl(null);
        setTaskStatus(null);
        localStorage.removeItem('lastVideoUrl');
        setAnalysisStates(newStates);
    }, []);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: { 'image/*': ['.jpeg', '.png', '.jpg', '.webp'] }, multiple: true });

    const handleAnalyze = async () => {
        const imagesToAnalyze = analysisStates.filter(s => !s.result && !s.error);
        if (imagesToAnalyze.length === 0) {
            alert("분석할 새로운 이미지를 업로드해주세요.");
            return;
        }

        setIsAnalyzing(true);
        // ✅ [핵심 수정] try...finally 블록으로 전체 분석 과정을 감쌉니다.
        try {
            if (imagesToAnalyze.length === 1) {
                await analyzeSingleImage();
            } else {
                await analyzeMultipleImagesAsVideo();
            }
        } catch (error) {
            // analyzeMultipleImagesAsVideo에서 reject된 에러를 처리
            console.error("분석 프로세스 중 처리되지 않은 에러 발생:", error);
            // 대부분의 에러 메시지는 taskStatus에 이미 표시되므로 추가 alert는 생략합니다.
        } finally {
            // ✅ 성공하든, 실패하든, 모든 과정이 끝나면 반드시 실행됩니다.
            setIsAnalyzing(false);
        }
    };

    const analyzeSingleImage = async () => {
        const targetIndex = analysisStates.findIndex(s => !s.result && !s.error);
        if (targetIndex === -1) {
            // 분석할 이미지가 없는 경우 즉시 종료
            return;
        }

        // 개별 이미지의 로딩 상태를 true로 설정
        setAnalysisStates(prev => prev.map((s, i) => 
            i === targetIndex ? { ...s, isLoading: true, error: null } : s
        ));
        
        try {
            const base64Image = await fileToBase64(analysisStates[targetIndex].file);
            const res = await api.post(`/analyze`, { image: base64Image });
            
            // 성공 시 결과 업데이트 및 로딩 상태 false로 변경
            setAnalysisStates(prev => prev.map((s, i) => 
                i === targetIndex ? { ...s, result: res.data, isLoading: false } : s
            ));
        } catch (err: any) {
            const msg = err.response?.data?.detail || "분석 실패";
            
            // 실패 시 에러 메시지 업데이트 및 로딩 상태 false로 변경
            setAnalysisStates(prev => prev.map((s, i) => 
                i === targetIndex ? { ...s, error: msg, isLoading: false } : s
            ));
        }
    };
    
    const analyzeMultipleImagesAsVideo = (): Promise<void> => {
        return new Promise(async (resolve, reject) => {
            setTaskStatus("이미지들을 서버로 전송 중입니다...");
            try {
                const formData = new FormData();
                analysisStates.forEach((state) => {
                    console.log("전송 파일:", state.file.name, state.file.size);
                    formData.append("files", state.file);  // 실제 파일 자체를 전송
                });

                const res = await api.post(`/analyze_video`, formData, {
                    headers: { "Content-Type": "multipart/form-data" },
                    maxContentLength: Infinity,
                    maxBodyLength: Infinity
                });

                const { task_id, results } = res.data;
                if (results && results.length > 0){
                    setAnalysisStates(prev =>
                        prev.map(state => {
                            const match = results.find((r: { filename: string; detections: YoloAnalysisResult[] }) => r.filename === state.file.name);
                            return match ? { ...state, result: match.detections } : state;
                        })
                    );
                }
                setTaskStatus("동영상 생성 및 분석 중... (최대 몇 분 소요될 수 있습니다)");

                const intervalId = setInterval(async () => {
                    try {
                        const statusRes = await api.get(`/tasks/${task_id}/status`);
                        const { status, result, image_results } = statusRes.data;

                        if (status === 'SUCCESS' || status === 'FAILURE') {
                            clearInterval(intervalId);
                            if (status === 'SUCCESS') {
                                clearInterval(intervalId);
                                const finalUrl = `${API_BASE}${result}`;
                                setVideoUrl(finalUrl);
                                sessionStorage.setItem('lastVideoUrl', finalUrl);
                                if (image_results && image_results.length > 0) {
                                    setAnalysisStates(prev =>
                                        prev.map((s, i) => ({ ...s, result: image_results[i]?.detections || [] }))
                                    );
                                }
                                setTaskStatus("동영상 생성 및 분석 완료!");
                                resolve();
                            } else {
                                setTaskStatus(`오류 발생: ${result}`);
                                reject(new Error(result));
                            }
                        }
                    } catch (pollError) {
                        clearInterval(intervalId);
                        setTaskStatus("상태 확인 중 오류 발생");
                        reject(pollError);
                    }
                }, 5000);
            } catch (requestError: any) {
                setTaskStatus(requestError.response?.data?.detail || "동영상 분석 요청 실패");
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
                        
                        {state.result && state.result.length > 0 && (
                            <div className="absolute bottom-0 bg-black bg-opacity-60 text-white text-xs p-1.5 rounded-tl-lg">
                                {state.result.map((r, i) => (
                                    <p key={i}>{r.label} ({(r.confidence*100).toFixed(1)}%)</p>
                                ))}
                            </div>
                        )}

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
                                    {res.label} ({(res.confidence * 100).toFixed(1)}%)
                                </div>
                            </React.Fragment>
                        ))}
                        {state.result && state.result.length === 0 && <div className="absolute inset-0 flex items-center justify-center p-2 text-center text-white font-semibold bg-gray-600 bg-opacity-80">바나나를 찾지 못했습니다.</div>}
                    </div>
                ))}
            </div>
        </div>)}
    </div>)}
        
    