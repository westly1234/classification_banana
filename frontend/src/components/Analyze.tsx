// src/components/Analyze.tsx
import { useLayoutEffect, useState, useCallback, useEffect, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import { AnimatePresence, motion } from 'framer-motion';
import type { YoloAnalysisResult, ImageAnalysisResultPayload } from '../types';
import api from './api';
import { UploadCloud, Trash2, XCircle, Loader2, Image, Sparkles, Files } from 'lucide-react';
//import ReactPlayer from 'react-player';

interface AnalysisState {
  id: string;
  file: File | null; 
  previewUrl: string;
  result: YoloAnalysisResult[] | null;
  error: string | null;
  isLoading: boolean;
  isSelected: boolean;
  avg_confidence?: number;
}

type WithFile = AnalysisState & { file: File };

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

// Data URL로 변환 (새로고침 복원에 유리)
const fileToDataUrl = (file: File) =>
  new Promise<string>((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result as string);
    r.onerror = rej;
    r.readAsDataURL(file);
  });

// 스트립 상태를 얇게 저장해서 세션에 보존
type SlimState = Pick<AnalysisState, 'id' | 'previewUrl' | 'result' | 'avg_confidence'>;

const persistStrip = (arr: AnalysisState[]) => {
  const slim: SlimState[] = arr.map(({ id, previewUrl, result, avg_confidence }) => ({
    id, previewUrl, result, avg_confidence,
  }));
  sessionStorage.setItem('imageStrip', JSON.stringify(slim));
};

// 파일명 정규화(윈/유닉스)
const normBase = (s?: string) => (s ? s.split('\\').pop()!.split('/').pop()! : '');

// 서버 image_results를 현재 analysisStates에 반영
function mergeServerImageResults(
  prev: AnalysisState[],
  server: ImageAnalysisResultPayload[],
  idsToAnalyze?: Set<string>
) {
  const map = new Map(server.map(r => [normBase(r.filename), r]));
  const next = prev.map(s => {
    // 선택한 항목만 갱신하고 싶다면 필터
    if (idsToAnalyze && !idsToAnalyze.has(s.id)) return s;

    // analyze_video로 보낸 항목은 file이 있음(복원된 항목은 없음)
    if (!s.file) return s;

    const m = map.get(normBase(s.file.name));
    if (!m) return s;

    const dets = (m.detections ?? []).map(d => ({ ...d, label: d.ripeness }));

    // 진행 중에는 '검출 있음' 또는 '에러가 있으면' 완료로 처리
    const finished = m.processed === true || Boolean(m.error);

    return {
      ...s,
      result: dets,
      avg_confidence: m.avg_confidence ?? s.avg_confidence,
      error: m.error ?? null,        // ⬅️ 서버 에러 반영
      isLoading: !finished,          // ⬅️ 완료면 로딩 해제
    };
  });
  persistStrip(next);
  return next;
}

export default function Analyze() {
  const [analysisStates, setAnalysisStates] = useState<AnalysisState[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [mainViewerUrl, setMainViewerUrl] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const [serverSettings, setServerSettings] = useState<ServerSettings | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const hasSelectedItems = analysisStates.some(s => s.isSelected);
  const selected = analysisStates.find(s => s.id === activeId) || null;
  const hasDetectionsInSelected = (selected?.result?.length ?? 0) > 0;
  // const hasMedia = analysisStates.length > 0 || Boolean(mainViewerUrl || videoUrl);
  const leftColRef = useRef<HTMLDivElement | null>(null);
  const [leftColH] = useState(0);
  const imgWrapRef = useRef<HTMLDivElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [imgOverlay, setImgOverlay] = useState<{
    offX: number; offY: number; drawW: number; drawH: number;
  } | null>(null);

  // ✅ 컴포넌트 스코프에 선언 (JSX에서도 사용 가능)
  const calcOverlay = useCallback(() => {
    const wrapEl = imgWrapRef.current;
    const imgEl  = imgRef.current;
    if (!wrapEl || !imgEl) return;

    const wrap = wrapEl.getBoundingClientRect();
    const imgR = imgEl.getBoundingClientRect();

    setImgOverlay({
      offX: Math.round(imgR.left - wrap.left),
      offY: Math.round(imgR.top  - wrap.top),
      drawW: Math.round(imgR.width),
      drawH: Math.round(imgR.height),
    });
  }, []);


  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get<ServerSettings>('/settings/');
        setServerSettings(data);
      } catch { /* 무시 */ }
    })();
  }, []);

  useEffect(() => {
    const savedRel = sessionStorage.getItem('lastVideoUrl');
    if (savedRel) {
      const absolute = api.getUri({ url: savedRel }); // baseURL로 복원
      const withTs = `${absolute}?t=${Date.now()}`;
      setVideoUrl(withTs);
      setMainViewerUrl(withTs);
      setTaskStatus('이전 동영상 분석 결과를 불러왔습니다.');
    }
  }, []);

  useEffect(() => {
    const saved = sessionStorage.getItem('imageStrip');
    if (!saved) return;

    try {
      const arr = JSON.parse(saved) as SlimState[];
      if (!Array.isArray(arr) || arr.length === 0) return;

      setAnalysisStates(arr.map(a => ({
        id: a.id,
        file: null,                 // 복원 시에는 파일이 없음
        previewUrl: a.previewUrl,   // data URL
        result: a.result ?? null,
        error: null,
        isLoading: false,
        isSelected: false,
        avg_confidence: a.avg_confidence,
      })));

      // 미디어 뷰어 첫 장 보여주기
      setActiveId(arr[0]?.id ?? null);
      setMainViewerUrl(prev => prev ?? arr[0]?.previewUrl ?? null);
    } catch {}
  }, []);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isAnalyzing || pollRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isAnalyzing]);

  useLayoutEffect(() => {
    const roWrap = new ResizeObserver(() => calcOverlay());
    const roImg  = new ResizeObserver(() => calcOverlay());

    if (imgWrapRef.current) roWrap.observe(imgWrapRef.current);
    if (imgRef.current)     roImg.observe(imgRef.current);

    const onLoad = () => calcOverlay();
    imgRef.current?.addEventListener('load', onLoad);
    window.addEventListener('resize', calcOverlay);

    calcOverlay(); // 최초 1회

    return () => {
      roWrap.disconnect();
      roImg.disconnect();
      window.removeEventListener('resize', calcOverlay);
      imgRef.current?.removeEventListener('load', onLoad);
    };
  }, [calcOverlay]);

  // ✅ 관찰자/리스너 세팅
  useLayoutEffect(() => {
    const roWrap = new ResizeObserver(() => calcOverlay());
    if (imgWrapRef.current) roWrap.observe(imgWrapRef.current);

    const imgEl = imgRef.current;
    const onLoad = () => calcOverlay();
    imgEl?.addEventListener('load', onLoad);

    window.addEventListener('resize', calcOverlay);

    // 최초 1회 계산
    calcOverlay();

    return () => {
      roWrap.disconnect();
      window.removeEventListener('resize', calcOverlay);
      imgEl?.removeEventListener('load', onLoad);
    };
  }, [calcOverlay]);


  useEffect(() => {
    calcOverlay();
  }, [calcOverlay, mainViewerUrl, selected?.result, leftColH]);

  //const makeObjectUrl = (file: File) => URL.createObjectURL(file);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const filtered = acceptedFiles.filter(f => f.size > 0 && f.type.startsWith('image/'));
    if (filtered.length === 0) {
      setTaskStatus('이미지를 추가해 주세요.');
      return;
    }

    // previewUrl을 Data URL로 만들어 새로고침에도 남도록
    const newStates: AnalysisState[] = await Promise.all(
      filtered.map(async file => ({
        id: `${file.name}-${file.lastModified}-${Math.random()}`,
        file,
        previewUrl: await fileToDataUrl(file),   // ⬅️ 여기
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

      // 첫 업로드라면 뷰어에 첫 장 띄우기
      if (!mainViewerUrl || prev.length === 0) {
        setMainViewerUrl(newStates[0].previewUrl);
      }

      if (!activeId && prev.length === 0) {
        setActiveId(newStates[0].id);
      }

      persistStrip(combined);      // ⬅️ 세션 보존
      return combined;
    });
  }, [mainViewerUrl]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.jpeg', '.png', '.jpg', '.webp'] },
    multiple: true,
  });

  const handleAnalyze = async () => {
    const targets = analysisStates.filter(
      (s): s is AnalysisState & { file: File } =>
        !!s.file && s.file.size > 0 && !s.result && !s.error
    );
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

  const analyzeSingleImage = async (targetState: WithFile) => {
    setActiveId(targetState.id);  
    setMainViewerUrl(targetState.previewUrl);
    setAnalysisStates(prev =>
      prev.map(s => (s.id === targetState.id ? { ...s, isLoading: true, error: null } : s))
    );
    try {
      const base64Image = await fileToBase64(targetState.file);
      const res = await api.post<ImageAnalysisResultPayload>(`/analysis/analyze`, { image: base64Image }, { timeout: 60000 });
      const { detections, avg_confidence } = res.data;
      const formattedDetections = detections.map(d => ({ ...d, label: d.ripeness }));
      setAnalysisStates(prev => {
        const next =prev.map(s =>
          s.id === targetState.id
            ? { ...s, result: formattedDetections, avg_confidence: avg_confidence ?? 0, isLoading: false }
            : s
        );
        persistStrip(next);      // ⬅️
        return next;
      });
    } catch (err: any) {
        const msg =
          err.response?.data?.detail ||
          (err.code === 'ECONNABORTED' ? '요청 시간이 초과되었습니다. 잠시 후 다시 시도하세요.' : '분석 실패');
        setAnalysisStates(prev => {
          const next = prev.map(s =>
            s.id === targetState.id ? { ...s, error: msg, isLoading: false } : s
          );
          persistStrip(next);      // ⬅️
          return next;
        });
      }
  }
  const analyzeMultipleImagesAsVideo = (statesToAnalyze: WithFile[]): Promise<void> =>
    new Promise(async (reject) => {
      setTaskStatus('이미지 분석 및 동영상 생성 요청 중...');
      const idsToAnalyze = new Set(statesToAnalyze.map(s => s.id));
      setAnalysisStates(prev =>
        prev.map(s => (idsToAnalyze.has(s.id) ? { ...s, isLoading: true, error: null } : s))
      );
      try {
        const formData = new FormData();
        statesToAnalyze.forEach(s => { if (s.file) formData.append('files', s.file); });
        const res = await api.post<{ task_id: string; results: ImageAnalysisResultPayload[] }>(`/analysis/analyze_video`, formData, { timeout: 120000 });
        const { task_id, results } = res.data;
        const norm = (s: string) => s.split('\\').pop()!.split('/').pop()!
        const resultsMap = new Map(results.map(r => [norm(r.filename), r]));

        setAnalysisStates(prev => {
          const next = prev.map(s => {
            const key = s.file? norm(s.file.name) : undefined;
            const match = key ? resultsMap.get(key) : undefined;

            return match
              ? {
                  ...s,
                  result: match.detections.map(d => ({ ...d, label: d.ripeness })),
                  avg_confidence: match.avg_confidence ?? 0,
                  isLoading: false,
                  error: null,
                }
              : s;
          });
          persistStrip(next);                 // ⬅️
          return next;
        });
        setTaskStatus('동영상 생성 중...');
        setMainViewerUrl(null);
        setActiveId(null); 
        pollRef.current = window.setInterval(async () => {
          try {
            // 캐시 우회를 위해 ts 붙임
            const { data } = await api.get(`/tasks/${task_id}/status`, { params: { ts: Date.now() }, timeout: 60000 });

            // 1) PROCESSING 동안에도 썸네일을 계속 채우기
            if (Array.isArray(data.image_results) && data.image_results.length > 0) {
              setAnalysisStates(prev => mergeServerImageResults(prev, data.image_results, idsToAnalyze));
              
              // 진행률 문구 (검출됐거나 에러가 있는 이미지를 '완료'로 간주)
              const done = data.image_results.filter((r: any) =>  r?.processed === true|| r?.error).length;
              const total = statesToAnalyze.length;
              setTaskStatus(`분석 중... ${done}/${total}`);
            }

            // 2) 종료 처리
            if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;

              if (Array.isArray(data.image_results)) {
                setAnalysisStates(prev => mergeServerImageResults(prev, data.image_results, idsToAnalyze));
              }
              setIsAnalyzing(false);

              if (data.status === 'SUCCESS') {
                const finalRel = data.result; // "/results/xxx.mp4"
                const absolute = data.absolute_result ?? api.getUri({ url: finalRel });
                const once = absolute + `?t=${Date.now()}`;     // ✅ 1회만 버스터

                setVideoUrl(prev => prev ?? once);              // ✅ 이미 있으면 유지(재시작 방지)
                setMainViewerUrl(prev => prev ?? once);
                sessionStorage.setItem('lastVideoUrl', finalRel);
                setTaskStatus(null);
              } else {
                setTaskStatus('오류: 동영상 생성 실패');
              }
            }
          } catch (pollError) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setIsAnalyzing(false);
            setTaskStatus('상태 확인 중 오류');
            console.error(pollError);
          }
        }, 3000); // ⬅️ 3초 간격으로 폴링
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
    
    sessionStorage.removeItem('imageStrip');   // ⬅️
    sessionStorage.removeItem('lastVideoUrl');
  };

  const handleDeleteSelected = () => {
    setAnalysisStates(prev => {
      const kept = prev.filter(s => !s.isSelected);

      if (!kept.some(s => s.id === activeId)) {
        setActiveId(kept[0]?.id ?? null);
        setMainViewerUrl(kept[0]?.previewUrl ?? null);
      }
      persistStrip(kept);          // ⬅️

      return kept;
    });
  };

  return (
    <div className="bg-slate-50 min-h-screen flex flex-col font-sans">
      {(isAnalyzing || !!pollRef.current) && (
        <div
          role="status"
          aria-live="polite"
          className="fixed top-3 left-1/2 -translate-x-1/2 z-50
                     bg-amber-50 text-amber-700 border border-amber-300
                     rounded-full px-4 py-2 shadow"
        >
          이미지  분석/동영상 생성 중입니다. 새로고침이나 탭 이동을 피해주세요.
        </div>
      )}
      <main className="flex-grow grid grid-cols-1 lg:grid-cols-12 gap-6 p-4 sm:p-6">
        <div ref={leftColRef} className="lg:col-span-8 xl:col-span-9 flex flex-col gap-6">
          {/* 미디어 뷰어 */}
          <motion.div
            layout
            className={
              "bg-white rounded-2xl shadow-lg flex items-center justify-center relative overflow-hidden p-2 " +
              (hasDetectionsInSelected
                 ? "min-h-[320px] sm:min-h-[420px] md:min-h-[560px]"
                 : "min-h-[320px] sm:min-h-[480px] md:min-h-[600px]")
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
                <div className="w-full max-w-full aspect-video bg-black rounded-lg overflow-hidden">
                  <video
                    key={videoUrl || ''}              // ✅ URL 바뀔 때만 재마운트
                    src={videoUrl || undefined}
                    controls
                    playsInline
                    preload="metadata"                // ✅ 메모리 절약
                    autoPlay={false}                  // ✅ 끔
                    loop={false}                      // ✅ 끔
                    muted                             // 원하면 유지
                    className="w-full h-full object-contain rounded-lg bg-black"
                    onEnded={e => {                   // ✅ 끝에서 멈춤 보장
                      e.currentTarget.pause();
                      e.currentTarget.currentTime = e.currentTarget.duration;
                    }}
                    onError={(e: any) => {
                      console.error('video load error', e);
                      setTaskStatus('비디오 로드 실패 (네트워크/URL 확인)');
                    }}
                  />
                </div>
              ) : (
                // 이미지 + 박스
                <div ref={imgWrapRef} className="relative w-full h-full flex justify-center items-center">
                  <img
                    ref={imgRef}
                    src={mainViewerUrl}
                    alt="Main view"
                    className="max-h-[500px] w-auto object-contain rounded-lg"
                    onLoad={calcOverlay}
                  />
                  {imgOverlay && selected?.result?.length ? (
                    <div
                      className="absolute pointer-events-none z-10"
                      style={{
                        left: imgOverlay.offX,
                        top: imgOverlay.offY,
                        width: imgOverlay.drawW,
                        height: imgOverlay.drawH,
                      }}
                    >
                  {selected.result.map((det: any, i: number) => {
                    const { drawW, drawH } = imgOverlay;

                    // 1) 정규화 박스 보정(0~1 범위, 우/하단 넘침 방지)
                    const b = det.boundingBox ?? {};
                    const nx = Math.max(0, Math.min(1, Number(b.x) || 0));
                    const ny = Math.max(0, Math.min(1, Number(b.y) || 0));
                    const nw = Math.max(0, Math.min(1 - nx, Number(b.width) || 0));
                    const nh = Math.max(0, Math.min(1 - ny, Number(b.height) || 0));

                    // 2) 픽셀로 변환
                    let x1 = nx * drawW;
                    let y1 = ny * drawH;
                    let x2 = (nx + nw) * drawW;
                    let y2 = (ny + nh) * drawH;

                    // 3) 오버레이 경계로 한 번 더 클립 (라운딩/경계 오차 대비)
                    x1 = Math.max(0, Math.min(drawW - 1, x1));
                    y1 = Math.max(0, Math.min(drawH - 1, y1));
                    x2 = Math.max(x1 + 1, Math.min(drawW, x2));
                    y2 = Math.max(y1 + 1, Math.min(drawH, y2));

                    const x = Math.round(x1);
                    const y = Math.round(y1);
                    const w = Math.round(x2 - x1);
                    const h = Math.round(y2 - y1);

                    const LABEL_H = 18;

                    // 4) 라벨은 "박스 내부 좌표"로 배치
                    //    박스 위에 공간 있으면 위(-LABEL_H), 없으면 박스 안(0)
                    const labelTop = y - LABEL_H >= 0 ? -LABEL_H : 0;
                    return (
                      <div key={i} style={{ position:'absolute', left:x, top:y, width:w, height:h, border:'3px solid #FACC15', borderRadius:2, boxSizing: "border-box", overflow: 'hidden',}}>
                        <div
                          className="absolute bg-black/80 text-white text-xs px-1.5 rounded"
                          style={{ left: 0, top: labelTop, maxWidth: "100%", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", }} // 박스 위에 붙이고 화면 위로는 못 나가게
                        >
                          {det.ripeness} {(det.confidence * 100).toFixed(1)}%
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>
          )
        )}
            {taskStatus && !videoUrl && (
              <div className="absolute inset-0 bg-black/50 flex flex-col items-center justify-center text-white z-10 p-4">
                <Loader2 className="w-10 h-10 animate-spin mb-4" />
                <p className="text-lg font-semibold text-center">{taskStatus}</p>
              </div>
            )}
          </motion.div>

          {/* 썸네일 스트립 */}
          <div className="lg:col-span-8 xl:col-span-9 bg-white flex flex-col gap-6">
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
                  onClick={() => {
                    if (isAnalyzing) return;
                    setActiveId(state.id);
                    setMainViewerUrl(state.previewUrl);
                  }}
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

                    {state.result?.map((det, i) => {
                      const b = det.boundingBox;
                      const x = Math.max(0, Math.min(1, b.x));
                      const y = Math.max(0, Math.min(1, b.y));
                      const w = Math.max(0, Math.min(1 - x, b.width));
                      const h = Math.max(0, Math.min(1 - y, b.height));
                      return (
                        <div
                          key={i}
                          className="absolute border-[3px] md:border-4 border-yellow-400 rounded-sm"
                          style={{
                            left: `${x * 100}%`,
                            top: `${y * 100}%`,
                            width: `${w * 100}%`,
                            height: `${h * 100}%`,
                          }}
                        >
                          <div
                            className="absolute bg-black/80 text-white text-[10px] sm:text-xs px-1.5 rounded font-semibold whitespace-nowrap"
                            style={{
                              left: 0,
                              top: Math.max(0, -1 + 0),   // 필요 시 고정 라벨 높이만큼 더 내리고 싶으면 숫자(예: 18) 사용
                            }}
                          >
                            {det.ripeness} {Number((det.confidence * 100).toFixed(1))}%
                        </div>
                      </div>
                      );
                    })}
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
        <aside
          className="lg:col-span-4 xl:col-span-3 bg-white rounded-2xl shadow-lg p-4 sm:p-6
                    flex flex-col sticky top-6 overflow-auto
                    max-h-[calc(100vh-1.5rem)]">
          <h2 className="text-lg sm:text-2xl font-bold text-slate-900 mb-3">제어판</h2>
          <div
            {...getRootProps()}
            className={`flex-1 min-h-[300px] sm:min-h-[360px] lg:min-h-[420px]
              border-2 border-dashed rounded-xl p-6 w-full
              text-center flex flex-col justify-center items-center cursor-pointer
              transition-all duration-300 ${isDragActive ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 hover:border-indigo-400'}`}>
            <input {...getInputProps()} />
            <UploadCloud className="w-12 h-12 mx-auto mb-2 text-slate-400" />
            <p className="font-semibold text-slate-700">클릭 또는 드래그하여 파일 추가</p>
            <p className="text-xs text-slate-500 mt-1">PNG, JPG, WEBP 지원</p>
            {serverSettings && (
              <p className="text-[11px] text-slate-400 mt-1">
                서버 제한:&nbsp;
                {serverSettings.MAX_FILES === 0
                  ? '개수 무제한'
                  : `최대 ${serverSettings.MAX_FILES}장`}
                ,&nbsp;
                {serverSettings.MAX_BYTES === 0
                  ? '용량 무제한'
                  : `파일당 ${(serverSettings.MAX_BYTES / (1024*1024)).toFixed(1)} MB`}
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