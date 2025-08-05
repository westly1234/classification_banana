import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { AnimatePresence, motion } from 'framer-motion';
import type { YoloAnalysisResult, ImageAnalysisResultPayload } from '../types';
import api from './api';
import { UploadCloud, Trash2, XCircle, Loader2, PlayCircle, Image, CheckCircle, Sparkles, Files } from 'lucide-react';

// --- 모든 로직 및 상태 관련 코드는 원본과 100% 동일하게 유지 ---

interface AnalysisState {
    id: string; file: File; previewUrl: string; result: YoloAnalysisResult[] | null;
    error: string | null; isLoading: boolean; isSelected: boolean; avg_confidence?: number;
}
type StorableAnalysisState = Omit<AnalysisState, 'file'> & { fileName: string, fileType: string };
const API_BASE = "http://127.0.0.1:8000";

const fileToBase64 = (file: File): Promise<string> => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
        const result = reader.result as string;
        if (!result || !result.includes(",")) reject("Base64 변환 실패");
        else resolve(result.split(",")[1]);
    };
    reader.onerror = error => reject(error);
});

export default function Analyze() {
    const [analysisStates, setAnalysisStates] = useState<AnalysisState[]>([]);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [videoUrl, setVideoUrl] = useState<string | null>(null);
    const [taskStatus, setTaskStatus] = useState<string | null>(null);
    const [mainViewerUrl, setMainViewerUrl] = useState<string | null>(null);

    // --- 모든 로직 원본 유지 ---
    useEffect(() => {
        const savedStatesJSON = sessionStorage.getItem('analysisStates');
        const savedVideoUrl = sessionStorage.getItem('lastVideoUrl');
        if (savedStatesJSON) {
            const savedStates: StorableAnalysisState[] = JSON.parse(savedStatesJSON);
            const restoredStates: AnalysisState[] = savedStates.map(s => ({ ...s, file: new File([], s.fileName, { type: s.fileType }), previewUrl: s.previewUrl }));
            setAnalysisStates(restoredStates);
            if (restoredStates.length > 0 && !savedVideoUrl) setMainViewerUrl(restoredStates[0].previewUrl);
        }
        if (savedVideoUrl) {
            setVideoUrl(savedVideoUrl); setMainViewerUrl(savedVideoUrl); setTaskStatus('이전 동영상 분석 결과를 불러왔습니다.');
        }
    }, []);

    useEffect(() => {
        if (analysisStates.length > 0) {
            const storableStates: StorableAnalysisState[] = analysisStates.map(({ file, ...rest }) => ({ ...rest, fileName: file.name, fileType: file.type }));
            sessionStorage.setItem('analysisStates', JSON.stringify(storableStates));
        } else { sessionStorage.removeItem('analysisStates'); }
    }, [analysisStates]);

    const fileToBase64Url = (file: File): Promise<string> => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = reject;
    });

    const onDrop = useCallback(async (acceptedFiles: File[]) => {
        const validFiles = acceptedFiles.filter(f => f.size > 0 && f.type.startsWith("image/"));
        if (validFiles.length === 0) return;
        const newStates: AnalysisState[] = await Promise.all(validFiles.map(async file => ({ id: `${file.name}-${file.lastModified}-${Math.random()}`, file, previewUrl: await fileToBase64Url(file), result: null, error: null, isLoading: false, isSelected: false, avg_confidence: undefined, })));
        setVideoUrl(null); setTaskStatus(null); sessionStorage.removeItem("lastVideoUrl");
        setAnalysisStates(prev => [...prev, ...newStates]);
        if (!mainViewerUrl || prev.length === 0) setMainViewerUrl(newStates[0].previewUrl);
    }, [mainViewerUrl]);
    
    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: { 'image/*': ['.jpeg', '.png', '.jpg', '.webp'] }, multiple: true });

    const handleAnalyze = async () => {
        const statesToAnalyze = analysisStates.filter(s => s.file?.size > 0 && !s.result && !s.error);
        if (statesToAnalyze.length === 0) return;
        setIsAnalyzing(true); setMainViewerUrl(null);
        try {
            if (statesToAnalyze.length === 1) await analyzeSingleImage(statesToAnalyze[0]);
            else await analyzeMultipleImagesAsVideo(statesToAnalyze);
        } catch (error) { console.error("분석 프로세스 에러:", error); } 
        finally { setIsAnalyzing(false); }
    };

    const analyzeSingleImage = async (targetState: AnalysisState) => {
        setMainViewerUrl(targetState.previewUrl);
        setAnalysisStates(prev => prev.map(s => s.id === targetState.id ? { ...s, isLoading: true, error: null } : s));
        try {
            const base64Image = await fileToBase64(targetState.file);
            const res = await api.post<ImageAnalysisResultPayload>(`/analyze`, { image: base64Image });
            const { detections, avg_confidence } = res.data;
            const formattedDetections = detections.map(d => ({ ...d, label: d.ripeness }));
            setAnalysisStates(prev => prev.map(s => s.id === targetState.id ? { ...s, result: formattedDetections, avg_confidence: avg_confidence ?? 0, isLoading: false } : s));
        } catch (err: any) {
            const msg = err.response?.data?.detail || "분석 실패";
            setAnalysisStates(prev => prev.map(s => s.id === targetState.id ? { ...s, error: msg, isLoading: false } : s));
        }
    };
    
    const analyzeMultipleImagesAsVideo = (statesToAnalyze: AnalysisState[]): Promise<void> => new Promise(async (resolve, reject) => {
        setTaskStatus("이미지 분석 및 동영상 생성 요청 중...");
        const idsToAnalyze = new Set(statesToAnalyze.map(s => s.id));
        setAnalysisStates(prev => prev.map(s => idsToAnalyze.has(s.id) ? { ...s, isLoading: true, error: null } : s));
        try {
            const formData = new FormData(); statesToAnalyze.forEach(s => formData.append("files", s.file));
            const res = await api.post<{ task_id: string; results: ImageAnalysisResultPayload[] }>(`/analyze_video`, formData, { headers: { "Content-Type": "multipart/form-data" }});
            const { task_id, results } = res.data;
            const resultsMap = new Map(results.map(r => [r.filename, r]));
            setAnalysisStates(prev => prev.map(s => {
                const match = resultsMap.get(s.file.name);
                return match ? { ...s, result: match.detections.map(d => ({ ...d, label: d.ripeness })), avg_confidence: match.avg_confidence ?? 0, isLoading: false, error: null } : s;
            }));
            setTaskStatus("동영상 생성 중..."); setMainViewerUrl(null);
            const intervalId = setInterval(async () => {
                try {
                    const { data } = await api.get(`/tasks/${task_id}/status`);
                    if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
                        clearInterval(intervalId);
                        if (data.status === 'SUCCESS') {
                            const finalUrl = `${API_BASE}${data.result}`;
                            setVideoUrl(finalUrl); setMainViewerUrl(finalUrl); sessionStorage.setItem('lastVideoUrl', finalUrl); setTaskStatus("동영상 생성 완료!"); resolve();
                        } else { setTaskStatus(`오류: 동영상 생성 실패`); reject(new Error(data.result)); }
                    }
                } catch (pollError) { clearInterval(intervalId); setTaskStatus("상태 확인 중 오류"); reject(pollError); }
            }, 3000);
        } catch (reqError: any) {
            const msg = reqError.response?.data?.detail || "요청 실패";
            setTaskStatus(msg); setAnalysisStates(prev => prev.map(s => idsToAnalyze.has(s.id) ? { ...s, isLoading: false, error: msg } : s)); reject(reqError);
        }
    });

    const handleClearAll = () => { setAnalysisStates([]); setVideoUrl(null); setTaskStatus(null); setMainViewerUrl(null); sessionStorage.clear(); };
    const handleDeleteSelected = () => { setAnalysisStates(prev => { const newStates = prev.filter(s => !s.isSelected); if (mainViewerUrl && !newStates.some(s => s.previewUrl === mainViewerUrl)) setMainViewerUrl(newStates[0]?.previewUrl || null); return newStates; }); };
    const hasSelectedItems = analysisStates.some(s => s.isSelected);
    
    return (
        <div className="bg-slate-50 h-screen max-h-screen overflow-hidden flex flex-col font-sans">
            <main className="flex-grow grid grid-cols-1 lg:grid-cols-12 gap-6 p-6 overflow-hidden">
                
                {/* Left Column: Workspace */}
                <div className="lg:col-span-8 xl:col-span-9 flex flex-col gap-6 overflow-hidden">
                    {/* Main Viewer */}
                    {/* ✅✅✅ 여기가 수정된 부분입니다: bg-slate-900 -> bg-white ✅✅✅ */}
                    <motion.div layout className="flex-grow bg-white rounded-2xl shadow-lg flex items-center justify-center relative overflow-hidden p-2">
                         <AnimatePresence>
                            {!mainViewerUrl && (
                                <motion.div key="placeholder" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }} className="text-center text-slate-400">
                                    <Image className="w-20 h-20 mb-4 mx-auto" />
                                    <h2 className="text-xl font-bold text-slate-600">미디어 뷰어</h2>
                                    <p className="text-slate-500">분석할 이미지를 선택하거나 동영상 결과를 확인하세요.</p>
                                </motion.div>
                            )}
                        </AnimatePresence>
                        {mainViewerUrl && (mainViewerUrl === videoUrl ? (
                            <video key={mainViewerUrl} controls autoPlay muted loop className="w-full h-full object-contain rounded-lg"><source src={`${mainViewerUrl}?t=${Date.now()}`} type="video/mp4" /></video>
                        ) : (
                            <img src={mainViewerUrl} alt="Main view" className="w-full h-full object-contain rounded-lg" />
                        ))}
                         {taskStatus && !videoUrl && (
                            <div className="absolute inset-0 bg-black/50 flex flex-col items-center justify-center text-white z-10 p-4">
                               <Loader2 className="w-10 h-10 animate-spin mb-4" />
                               <p className="text-lg font-semibold text-center">{taskStatus}</p>
                            </div>
                         )}
                    </motion.div>
                    
                    {/* Film Strip */}
                    <motion.div layout className="flex-shrink-0 bg-white rounded-2xl shadow-lg p-4">
                        <div className="flex items-center gap-3 mb-2">
                           <Files className="w-5 h-5 text-slate-500" />
                           <h3 className="text-md font-bold text-slate-700">이미지 스트립 ({analysisStates.length})</h3>
                        </div>
                        <div className="flex items-center gap-4 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-slate-200 hover:scrollbar-thumb-slate-300 scrollbar-track-slate-50">
                            {analysisStates.length === 0 ? (
                                <div className="w-full text-center text-slate-400 py-10">업로드된 이미지가 없습니다.</div>
                            ) : (
                                analysisStates.map((state) => (
                                    <motion.div key={state.id} layout onClick={() => !isAnalyzing && setMainViewerUrl(state.previewUrl)} onDoubleClick={() => state.file?.size > 0 && analyzeSingleImage(state)} className={`flex-shrink-0 w-32 h-32 rounded-xl overflow-hidden cursor-pointer relative group transition-all duration-200 ${mainViewerUrl === state.previewUrl ? 'ring-4 ring-indigo-500 ring-offset-2' : 'ring-2 ring-transparent hover:ring-indigo-400'}`}>
                                        <img src={state.previewUrl} alt="분석 이미지" className="w-full h-full object-cover" />
                                        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"/>
                                        
                                        {state.isLoading && <div className="absolute inset-0 bg-black/60 flex items-center justify-center"><Loader2 className="animate-spin text-white h-8 w-8" /></div>}
                                        {state.error && <div className="absolute inset-0 bg-rose-800/80 flex p-2 text-center text-white text-xs items-center justify-center font-semibold">{state.error}</div>}
                                        {state.result && state.result.length === 0 && <div className="absolute inset-0 bg-slate-600/80 flex p-2 text-center text-white text-xs items-center justify-center font-semibold">감지 실패</div>}

                                        {state.avg_confidence !== undefined && (
                                            <div className="absolute bottom-1.5 left-2 right-2 text-white text-xs font-bold flex justify-between items-center drop-shadow-lg">
                                                <span className="text-emerald-300">정확도</span>
                                                <span>{(state.avg_confidence * 100).toFixed(0)}%</span>
                                            </div>
                                        )}
                                        <button onClick={(e) => { e.stopPropagation(); setAnalysisStates(prev => prev.map(s => s.id === state.id ? {...s, isSelected: !s.isSelected} : s))}} className={`absolute top-2 right-2 w-5 h-5 rounded-full border-2 transition-all ${state.isSelected ? 'bg-indigo-500 border-white' : 'bg-black/30 border-slate-400 group-hover:bg-black/50'}`}>
                                            {state.isSelected && <CheckCircle size={16} className="text-white transform scale-125" />}
                                        </button>
                                    </motion.div>
                                ))
                            )}
                        </div>
                    </motion.div>
                </div>

                 {/* Right Column: Control Panel */}
                 <aside className="lg:col-span-4 xl:col-span-3 bg-white rounded-2xl shadow-lg flex flex-col p-6">
                    <header className="mb-6">
                        <h1 className="text-3xl font-extrabold text-slate-900">제어판</h1>
                        <p className="mt-1 text-slate-500">이미지를 추가하고 분석을 실행하세요.</p>
                    </header>
                    <div {...getRootProps()} className={`flex-grow border-2 border-dashed rounded-xl p-6 text-center flex flex-col justify-center items-center cursor-pointer transition-all duration-300 ${isDragActive ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 hover:border-indigo-400'}`}>
                        <input {...getInputProps()} />
                        <UploadCloud className={`w-12 h-12 mx-auto mb-2 transition-colors ${isDragActive ? 'text-indigo-500' : 'text-slate-400'}`} />
                        <p className="font-semibold text-slate-700">{isDragActive ? "여기에 파일을 놓으세요!" : "클릭 또는 드래그하여 파일 추가"}</p>
                        <p className="text-xs text-slate-500 mt-1">PNG, JPG, WEBP 지원</p>
                    </div>
                    {analysisStates.length > 0 && (
                        <div className="mt-6 space-y-4">
                            <motion.button whileTap={{ scale: 0.98 }} onClick={handleAnalyze} disabled={isAnalyzing} className="w-full flex items-center justify-center gap-2 text-lg px-6 py-3 bg-indigo-600 text-white font-bold rounded-lg hover:bg-indigo-700 disabled:bg-slate-400 transition-all shadow-lg hover:shadow-indigo-500/50">
                                {isAnalyzing ? <Loader2 className="animate-spin" /> : <Sparkles />}
                                분석 실행 ({analysisStates.filter(s => s.file.size > 0 && !s.result && !s.error).length})
                            </motion.button>
                            <div className="grid grid-cols-2 gap-4">
                                <button onClick={handleDeleteSelected} disabled={isAnalyzing || !hasSelectedItems} className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-slate-200 text-slate-700 font-semibold rounded-lg hover:bg-slate-300 disabled:bg-slate-100 disabled:text-slate-400">
                                    <Trash2 size={16} /> 선택 삭제
                                </button>
                                <button onClick={handleClearAll} disabled={isAnalyzing} className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-rose-100 text-rose-600 font-semibold rounded-lg hover:bg-rose-200 disabled:bg-slate-100">
                                    <XCircle size={16} /> 전체 삭제
                                </button>
                            </div>
                        </div>
                    )}
                </aside>

            </main>
        </div>
    );
}