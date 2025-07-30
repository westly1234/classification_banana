import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import type { YoloAnalysisResult } from '../types';
import ReactPlayer from 'react-player';

// ✅ [수정] AnalysisState의 result 타입을 배열로 변경
interface AnalysisState {
    id: string;
    file: File;
    previewUrl: string;
    result: YoloAnalysisResult[] | null; // 단일 객체가 아닌 배열
    error: string | null;
    isLoading: boolean;
    isSelected: boolean;
}

const API_BASE = "http://localhost:8000";
// api.ts를 사용한다고 가정, 없다면 이전 답변을 참고하여 생성해주세요.
import api from './api'; 

const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve((reader.result as string).split(',')[1]);
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
        return () => {
            analysisStates.forEach(state => URL.revokeObjectURL(state.previewUrl));
        };
    }, [analysisStates]);

    const onDrop = useCallback((acceptedFiles: File[]) => {
        const newStates: AnalysisState[] = acceptedFiles.map(file => ({
            id: `${file.name}-${file.lastModified}-${Math.random()}`,
            file,
            previewUrl: URL.createObjectURL(file),
            result: null, error: null, isLoading: false, isSelected: false,
        }));
        setVideoUrl(null);
        setTaskStatus(null);
        setAnalysisStates(prev => [...prev, ...newStates]);
    }, []);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: { 'image/*': ['.jpeg', '.png', '.jpg', '.webp'] }, multiple: true });

    const handleAnalyze = async () => {
        const imagesToAnalyze = analysisStates.filter(s => !s.result && !s.error);
        if (imagesToAnalyze.length === 0) {
            alert("분석할 새로운 이미지를 업로드해주세요.");
            return;
        }
        setIsAnalyzing(true);
        if (imagesToAnalyze.length === 1) {
            await analyzeSingleImage();
        } else {
            await analyzeMultipleImagesAsVideo();
        }
        setIsAnalyzing(false);
    };

    const analyzeSingleImage = async () => {
        const targetIndex = analysisStates.findIndex(s => !s.result && !s.error);
        if (targetIndex === -1) return;

        setAnalysisStates(prev => prev.map((s, i) => i === targetIndex ? { ...s, isLoading: true, error: null } : s));
        try {
            const base64Image = await fileToBase64(analysisStates[targetIndex].file);
            const res = await api.post(`/analyze`, { image: base64Image });
            setAnalysisStates(prev => prev.map((s, i) => i === targetIndex ? { ...s, result: res.data, isLoading: false } : s));
        } catch (err: any) {
            const msg = err.response?.data?.detail || "분석 실패";
            setAnalysisStates(prev => prev.map((s, i) => i === targetIndex ? { ...s, error: msg, isLoading: false } : s));
        }
    };
    
    const analyzeMultipleImagesAsVideo = async () => {
        setTaskStatus("이미지들을 서버로 전송 중입니다...");
        try {
            const imagesToProcess = analysisStates.filter(s => !s.result && !s.error);
            const imagePromises = imagesToProcess.map(state => fileToBase64(state.file));
            const base64Images = await Promise.all(imagePromises);
            const res = await api.post(`/analyze_video`, { images: base64Images });
            const { task_id } = res.data;
            setTaskStatus("동영상 생성 및 분석 중... (최대 몇 분 소요될 수 있습니다.)");
            const intervalId = setInterval(async () => {
                try {
                    const statusRes = await api.get(`/tasks/${task_id}/status`);
                    const { status, result } = statusRes.data;
                    if (status === 'SUCCESS' || status === 'FAILURE') {
                        clearInterval(intervalId);
                        if (status === 'SUCCESS') {
                            setVideoUrl(`${API_BASE}${result}`);
                            setTaskStatus("동영상 생성 및 분석 완료!");
                        } else { setTaskStatus(`오류 발생: ${result}`); }
                    }
                } catch { clearInterval(intervalId); setTaskStatus("상태 확인 중 오류 발생"); }
            }, 5000);
        } catch (err: any) { setTaskStatus(err.response?.data?.detail || "동영상 분석 요청 실패"); }
    };

    const handleToggleSelect = (id: string) => setAnalysisStates(prev => prev.map(s => (s.id === id ? { ...s, isSelected: !s.isSelected } : s)));
    const handleDeleteSelected = () => setAnalysisStates(prev => prev.filter(s => !s.isSelected));
    const handleClearAll = () => setAnalysisStates([]);
    const hasSelectedItems = analysisStates.some(state => state.isSelected);

    return (
        <div className="max-w-7xl mx-auto p-4 md:p-8">
            <div className="text-center mb-10"><h1 className="text-4xl font-extrabold text-brand-gray-900">바나나 상태 분류기</h1><p className="mt-2 text-lg text-brand-gray-600">한 장의 사진은 개별 분석, 여러 장은 동영상으로 분석됩니다.</p></div>
            <div {...getRootProps()} className={`bg-white p-6 md:p-8 rounded-2xl shadow-lg border-4 border-dashed cursor-pointer transition-colors duration-300 mb-8 ${isDragActive ? 'border-yellow-400 bg-yellow-50' : 'border-gray-300 hover:border-yellow-400'}`}>
                <input {...getInputProps()} /><div className="flex flex-col items-center justify-center text-center"><svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg><p className="mt-4 text-lg text-gray-600">이미지들을 드래그 앤 드롭하거나 클릭해서 선택하세요</p><p className="text-sm text-gray-400 mt-1">PNG, JPG, WEBP 최대 10MB</p></div>
            </div>
            {analysisStates.length > 0 && (<div><div className="flex justify-between items-center mb-6"><h2 className="text-2xl font-bold">분석 대상 ({analysisStates.length}개)</h2><div className="flex gap-4"><button onClick={handleDeleteSelected} disabled={isAnalyzing || !hasSelectedItems} className="px-6 py-2 bg-gray-300 text-gray-800 font-semibold rounded-lg hover:bg-gray-400 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed">선택 삭제</button><button onClick={handleClearAll} disabled={isAnalyzing} className="px-6 py-2 bg-red-500 text-white font-semibold rounded-lg hover:bg-red-600 disabled:bg-gray-400">전체 삭제</button><button onClick={handleAnalyze} disabled={isAnalyzing} className="px-6 py-2 bg-yellow-400 text-gray-900 font-bold rounded-lg hover:bg-yellow-500 disabled:bg-gray-400">{isAnalyzing ? '분석 중...' : '분석하기'}</button></div></div>
            {videoUrl ? (<div className="mt-6 bg-white p-4 rounded-lg shadow-lg"><h3 className="text-center mb-4 text-xl font-semibold text-blue-800">{taskStatus}</h3><ReactPlayer key={videoUrl} url={videoUrl} controls={true} playing={true} width="100%" height="auto" /></div>) : (<div>{taskStatus && <div className="text-center my-4 p-4 bg-blue-100 text-blue-800 rounded-lg font-semibold">{taskStatus}</div>}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                {analysisStates.map((state) => (
                    <div key={state.id} onClick={() => !isAnalyzing && handleToggleSelect(state.id)} className={`relative rounded-lg overflow-hidden cursor-pointer transition-all w-full shadow-md ${state.isSelected ? 'ring-4 ring-blue-500 ring-offset-2' : ''}`} style={{ aspectRatio: '1 / 1' }}>
                        <img src={state.previewUrl} alt={`분석 이미지`} className="w-full h-full object-cover" />
                        {state.isLoading && <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white"></div></div>}
                        {state.error && <div className="absolute inset-0 flex items-center justify-center p-2 text-center text-white font-semibold bg-red-800 bg-opacity-80">{state.error}</div>}
                        
                        {/* ✅ [핵심 수정] 결과가 배열인지, 빈 배열인지, 요소가 있는지에 따라 분기 처리 */}
                        {state.result && state.result.length > 0 && state.result.map((res, index) => (
                            <React.Fragment key={index}>
                                <div className="absolute border-4 border-yellow-400 rounded-md" style={{ top: `${res.boundingBox.y * 100}%`, left: `${res.boundingBox.x * 100}%`, width: `${res.boundingBox.width * 100}%`, height: `${res.boundingBox.height * 100}%` }}></div>
                                <div className="absolute bottom-0 right-0 bg-black bg-opacity-60 text-white text-xs p-1.5 rounded-tl-lg">
                                    <p className="font-bold">{res.ripeness}</p>
                                    <p>{(res.confidence * 100).toFixed(1)}%</p>
                                </div>
                            </React.Fragment>
                        ))}
                        {state.result && state.result.length === 0 && <div className="absolute inset-0 flex items-center justify-center p-2 text-center text-white font-semibold bg-gray-600 bg-opacity-80">바나나를 찾지 못했습니다.</div>}
                    </div>
                ))}
            </div></div>)}</div>)}
        </div>
    );
}