// src/components/Analyze.tsx
import { useState, useCallback, useEffect, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import { AnimatePresence, motion } from 'framer-motion';
import type { YoloAnalysisResult, ImageAnalysisResultPayload } from '../types';
import api, { API_BASE } from './api';
import { UploadCloud, Trash2, XCircle, Loader2, Image, Sparkles, Files } from 'lucide-react';
import ReactPlayer from 'react-player';

interface AnalysisState {
  id: string;
  file: File;
  previewUrl: string;
  result: YoloAnalysisResult[] | null;
  error: string | null;
  isLoading: boolean;
  isSelected: boolean;
  avg_confidence?: number;
}
type ServerSettings = {
  MAX_FILES: number;
  MAX_BYTES: number;
};

const fileToBase64 = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const result = reader.result as string;
      if (!result || !result.includes(',')) reject('Base64 변환 실패');
      else resolve(result.split(',')[1]);
    };
    reader.onerror = error => reject(error);
  });

export default function Analyze() {
  const [analysisStates, setAnalysisStates] = useState<AnalysisState[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [mainViewerUrl, setMainViewerUrl] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const [serverSettings, setServerSettings] = useState<ServerSettings | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      // object URL 정리
      analysisStates.forEach(s => { try { URL.revokeObjectURL(s.previewUrl); } catch {} });
    };
  }, [analysisStates]);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get<ServerSettings>('/settings');
        setServerSettings(data);
      } catch { /* 무시 */ }
    })();
  }, []);

  useEffect(() => {
    const savedVideoUrl = sessionStorage.getItem('lastVideoUrl');
    if (savedVideoUrl) {
      setVideoUrl(savedVideoUrl);
      setMainViewerUrl(savedVideoUrl);
      setTaskStatus('이전 동영상 분석 결과를 불러왔습니다.');
    }
  }, []);

  const makeObjectUrl = (file: File) => URL.createObjectURL(file);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const filtered = acceptedFiles
      .filter(f => f.size > 0 && f.type.startsWith('image/'));  // 크기/개수 필터 제거

    if (filtered.length === 0) {
      setTaskStatus(`이미지를 추가해 주세요.`);
      return;
    }

    const newStates: AnalysisState[] = await Promise.all(
      filtered.map(async file => ({
        id: `${file.name}-${file.lastModified}-${Math.random()}`,
        file,
        previewUrl: makeObjectUrl(file),
        result: null,
        error: null,
        isLoading: false,
        isSelected: false,
        avg_confidence: undefined,
      }))
    );

    setVideoUrl(null);
    setTaskStatus(null);
    sessionStorage.removeItem('lastVideoUrl');

    setAnalysisStates(prev => {
      const combined = [...prev, ...newStates];
      if (!mainViewerUrl || prev.length === 0) {
        setMainViewerUrl(newStates[0].previewUrl);
      }
      return combined;
    });
  }, [mainViewerUrl]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.jpeg', '.png', '.jpg', '.webp'] },
    multiple: true,
  });

  const handleAnalyze = async () => {
    const targets = analysisStates.filter(s => s.file?.size > 0 && !s.result && !s.error);
    if (targets.length === 0) return;

    setIsAnalyzing(true);
    setMainViewerUrl(null);
    try {
      if (targets.length === 1) await analyzeSingleImage(targets[0]);
      else await analyzeMultipleImagesAsVideo(targets);
    } catch (e) {
      console.error('분석 중 오류', e);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const analyzeSingleImage = async (targetState: AnalysisState) => {
    setMainViewerUrl(targetState.previewUrl);
    setAnalysisStates(prev =>
      prev.map(s => (s.id === targetState.id ? { ...s, isLoading: true, error: null } : s))
    );
    try {
      const base64Image = await fileToBase64(targetState.file);
      const res = await api.post<ImageAnalysisResultPayload>(`/analysis/analyze`, { image: base64Image }, { timeout: 60000 });
      const { detections, avg_confidence } = res.data;
      const formattedDetections = detections.map(d => ({ ...d, label: d.ripeness }));
      setAnalysisStates(prev =>
        prev.map(s =>
          s.id === targetState.id
            ? { ...s, result: formattedDetections, avg_confidence: avg_confidence ?? 0, isLoading: false }
            : s
        )
      );
    } catch (err: any) {
        const msg =
          err.response?.data?.detail ||
          (err.code === 'ECONNABORTED' ? '요청 시간이 초과되었습니다. 잠시 후 다시 시도하세요.' : '분석 실패');
        setAnalysisStates(prev =>
        prev.map(s => (s.id === targetState.id ? { ...s, error: msg, isLoading: false } : s))
      );
    }
  };

  const analyzeMultipleImagesAsVideo = (statesToAnalyze: AnalysisState[]): Promise<void> =>
    new Promise(async (resolve, reject) => {
      setTaskStatus('이미지 분석 및 동영상 생성 요청 중...');
      const idsToAnalyze = new Set(statesToAnalyze.map(s => s.id));
      setAnalysisStates(prev =>
        prev.map(s => (idsToAnalyze.has(s.id) ? { ...s, isLoading: true, error: null } : s))
      );
      try {
        const formData = new FormData();
        statesToAnalyze.forEach(s => formData.append('files', s.file));
        const res = await api.post<{ task_id: string; results: ImageAnalysisResultPayload[] }>(`/analysis/analyze_video`, formData, { timeout: 120000 });
        const { task_id, results } = res.data;
        const resultsMap = new Map(results.map(r => [r.filename, r]));
        setAnalysisStates(prev =>
          prev.map(s => {
            const match = resultsMap.get(s.file.name);
            return match
              ? {
                  ...s,
                  result: match.detections.map(d => ({ ...d, label: d.ripeness })),
                  avg_confidence: match.avg_confidence ?? 0,
                  isLoading: false,
                  error: null,
                }
              : s;
          })
        );
        setTaskStatus('동영상 생성 중...');
        setMainViewerUrl(null);
        pollRef.current = window.setInterval(async () => {
          try {
            const { data } = await api.get(`/tasks/${task_id}/status`);
            if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;

              if (data.status === 'SUCCESS') {
                const makeAbsolute = (p: string) =>
                  /^https?:\/\//i.test(p)
                    ? p
                    : `${API_BASE.replace(/\/+$/, "")}${p.startsWith("/") ? "" : "/"}${p}`; 
                const finalUrl = makeAbsolute(data.result);
                setVideoUrl(finalUrl);
                setMainViewerUrl(finalUrl);
                sessionStorage.setItem('lastVideoUrl', finalUrl);
                setTaskStatus('동영상 생성 완료!');
                resolve();
              } else {
                setTaskStatus(`오류: 동영상 생성 실패`);
                reject(new Error(data.result));
              }
            }
          } catch (pollError) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setTaskStatus('상태 확인 중 오류');
            reject(pollError);
          }
        }, 3000);
      } catch (reqError: any) {
        const msg = reqError.response?.data?.detail ||   (reqError.code === 'ECONNABORTED' ? '요청 시간이 초과되었습니다. 잠시 후 다시 시도하세요.' :
          '서버가 바쁘거나 일시적으로 중단되었습니다. 잠시 후 다시 시도하세요.');
        setTaskStatus(msg);
        setAnalysisStates(prev =>
          prev.map(s =>
            idsToAnalyze.has(s.id) ? { ...s, isLoading: false, error: msg } : s
          )
        );
        setIsAnalyzing(false);
        reject(reqError);
      }
    });

  const handleClearAll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    setAnalysisStates([]);
    setVideoUrl(null);
    setTaskStatus(null);
    setMainViewerUrl(null);
    sessionStorage.clear();
  };

  const handleDeleteSelected = () => {
    setAnalysisStates(prev => {
      const newStates = prev.filter(s => !s.isSelected);
      if (mainViewerUrl && !newStates.some(s => s.previewUrl === mainViewerUrl)) {
        setMainViewerUrl(newStates[0]?.previewUrl || null);
      }
      return newStates;
    });
  };

  const hasSelectedItems = analysisStates.some(s => s.isSelected);

  const selected = analysisStates.find(s => s.previewUrl === mainViewerUrl);
  const hasDetectionsInSelected = (selected?.result?.length ?? 0) > 0;

  return (
    <div className="bg-slate-50 min-h-screen flex flex-col font-sans">
      <main className="flex-grow grid grid-cols-1 lg:grid-cols-12 gap-6 p-4 sm:p-6">
        <div className="lg:col-span-8 xl:col-span-9 flex flex-col gap-6">
          {/* 미디어 뷰어 */}
          <motion.div
            layout
            className={
              "bg-white rounded-2xl shadow-lg flex items-center justify-center relative overflow-hidden p-2 " +
              (hasDetectionsInSelected
                ? "min-h-[420px] sm:min-h-[560px] md:min-h-[680px]"   // 결과 크~게
                : "min-h-[240px] sm:min-h-[300px] md:min-h-[360px]")  // 미리보기 작게
            }
          >
            <AnimatePresence>
              {!mainViewerUrl && (
                <motion.div
                  key="placeholder"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  className="text-center text-slate-400"
                >
                  <Image className="w-20 h-20 mb-4 mx-auto" />
                  <h2 className="text-xl font-bold text-slate-600">미디어 뷰어</h2>
                  <p className="text-slate-500">이미지를 선택하거나 결과를 확인하세요.</p>
                </motion.div>
              )}
            </AnimatePresence>

            {mainViewerUrl &&
              (mainViewerUrl === videoUrl ? (
                // ✅ react-player로 교체 (캐시 방지 쿼리 유지)
                <div className="w-full h-full max-h-[500px]">
                  <ReactPlayer
                    url={`${mainViewerUrl}?t=${Date.now()}`}
                    controls
                    playing={false}
                    muted
                    loop
                    width="100%"
                    height="100%"
                  />
                </div>
              ) : (
                <img
                  src={mainViewerUrl}
                  alt="Main view"
                  className="w-full h-full object-contain rounded-lg"
                />
              ))}

            {taskStatus && !videoUrl && (
              <div className="absolute inset-0 bg-black/50 flex flex-col items-center justify-center text-white z-10 p-4">
                <Loader2 className="w-10 h-10 animate-spin mb-4" />
                <p className="text-lg font-semibold text-center">{taskStatus}</p>
              </div>
            )}
          </motion.div>

          {/* 썸네일 스트립 */}
          <div className="bg-white rounded-2xl shadow-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Files className="w-5 h-5 text-slate-500" />
              <h3 className="text-sm sm:text-md font-bold text-slate-700">
                이미지 스트립 ({analysisStates.length})
              </h3>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-slate-200 hover:scrollbar-thumb-slate-300 scrollbar-track-slate-50">
              {analysisStates.map(state => (
                <div
                  key={state.id}
                  onClick={() => !isAnalyzing && setMainViewerUrl(state.previewUrl)}
                  className={`relative flex-shrink-0 w-36 h-40 sm:w-40 sm:h-44 md:w-44 md:h-48 rounded-xl overflow-hidden cursor-pointer group border-2 ${
                    mainViewerUrl === state.previewUrl
                      ? 'border-indigo-500'
                      : 'border-transparent hover:border-indigo-300'
                  }`}
                >
                  <div
                    className="absolute top-1 left-1 z-10"
                    onClick={(e) => e.stopPropagation()} // 클릭 버블 방지
                  >
                    <input
                      type="checkbox"
                      checked={state.isSelected}
                      onChange={(e) => {
                        e.stopPropagation();
                        setAnalysisStates(prev =>
                          prev.map(s => s.id === state.id ? { ...s, isSelected: !s.isSelected } : s)
                        );
                      }}
                      className="w-4 h-4 accent-indigo-600"
                      aria-label="선택"
                    />
                  </div>
                  <div className="relative w-full h-full overflow-visible">
                    <img
                      src={state.previewUrl}
                      alt="preview"
                      className="w-full h-full object-cover"
                    />

                    {state.result?.map((det, i) => (
                      <div
                        key={i}
                        className="absolute border-[3px] md:border-4 border-yellow-400 rounded-sm"
                        style={{
                          left: `${det.boundingBox.x * 100}%`,
                          top: `${det.boundingBox.y * 100}%`,
                          width: `${det.boundingBox.width * 100}%`,
                          height: `${det.boundingBox.height * 100}%`,
                        }}
                      >
                        <div className="absolute top-0 left-0 bg-black/80 text-white text-[11px] sm:text-xs px-1.5 rounded-sm font-semibold whitespace-nowrap">
                          {det.ripeness} {Number((det.confidence * 100).toFixed(1))}%
                        </div>
                      </div>
                    ))}
                  </div>

                  {state.error && (
                    <div className="absolute inset-0 bg-red-700/80 text-xs text-white font-bold flex items-center justify-center">
                      {state.error}
                    </div>
                  )}

                  {state.avg_confidence !== undefined && (
                    <div className="absolute bottom-1 left-2 right-2 text-white text-[10px] sm:text-xs font-bold flex justify-between items-center drop-shadow">
                      <span className="text-emerald-300">정확도</span>
                      <span>{(state.avg_confidence * 100).toFixed(0)}%</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 제어판 */}
        <aside className="lg:col-span-4 xl:col-span-3 bg-white rounded-2xl shadow-lg p-4 sm:p-6 flex flex-col">
          <h2 className="text-lg sm:text-2xl font-bold text-slate-900 mb-3">제어판</h2>
          <div
            {...getRootProps()}
            className={`flex-grow border-2 border-dashed rounded-xl p-6 text-center flex flex-col justify-center items-center cursor-pointer transition-all duration-300 ${
              isDragActive ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 hover:border-indigo-400'
            }`}
          >
            <input {...getInputProps()} />
            <UploadCloud className="w-12 h-12 mx-auto mb-2 text-slate-400" />
            <p className="font-semibold text-slate-700">클릭 또는 드래그하여 파일 추가</p>
            <p className="text-xs text-slate-500 mt-1">PNG, JPG, WEBP 지원</p>
            {serverSettings && (
              <p className="text-[11px] text-slate-400 mt-1">
                서버 제한: {serverSettings.MAX_FILES === 0 ? '개수 무제한' : `최대 ${serverSettings.MAX_FILES}장`},
                {serverSettings.MAX_BYTES === 0 ? ' 용량 무제한' : ` 파일당 ${Math.floor(serverSettings.MAX_BYTES/1024/1024)}MB`}
              </p>
            )}
          </div>

          {analysisStates.length > 0 && (
            <div className="mt-6 space-y-4">
              <motion.button
                whileTap={{ scale: 0.98 }}
                onClick={handleAnalyze}
                disabled={isAnalyzing}
                className="w-full flex items-center justify-center gap-2 text-base px-4 py-2 bg-indigo-600 text-white font-bold rounded-lg hover:bg-indigo-700 disabled:bg-slate-400 transition-all"
              >
                {isAnalyzing ? <Loader2 className="animate-spin" /> : <Sparkles />}
                분석 실행
              </motion.button>
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={handleDeleteSelected}
                  disabled={isAnalyzing || !hasSelectedItems}
                  className="flex items-center justify-center gap-2 px-3 py-2 bg-slate-200 text-slate-700 text-sm font-semibold rounded-lg hover:bg-slate-300 disabled:bg-slate-100"
                >
                  <Trash2 size={14} />
                  선택 삭제
                </button>
                <button
                  onClick={handleClearAll}
                  disabled={isAnalyzing}
                  className="flex items-center justify-center gap-2 px-3 py-2 bg-rose-100 text-rose-600 text-sm font-semibold rounded-lg hover:bg-rose-200 disabled:bg-rose-50 disabled:text-rose-300"
                >
                  <XCircle size={14} />
                  전체 삭제
                </button>
              </div>
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}