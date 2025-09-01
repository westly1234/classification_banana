// src/components/Analyze.tsx
// ✅ 이미지/동영상이 "새로고침"이나 "다른 탭"에서도 살아있도록 전면 개선
// - 미디어(이미지 미리보기용 Blob)를 sessionStorage(Data URL) → IndexedDB(Blob) 저장으로 교체
// - 메타데이터(activeId, mainViewerUrl, lastVideoUrl, strip 순서)는 localStorage로 영구 보존
// - 새 탭에서도 동일 계정/도메인이라면 localStorage 동기화(storage 이벤트)로 즉시 복원
// - Object URL은 새로고침 시 사라지므로, 마운트 때 IndexedDB Blob로부터 재생성
// - 삭제/전체삭제 시 IndexedDB와 localStorage를 함께 정리

import { useLayoutEffect, useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { useDropzone } from 'react-dropzone';
import { AnimatePresence, motion } from 'framer-motion';
import type { YoloAnalysisResult, ImageAnalysisResultPayload } from '../types';
import api from './api';
import { matchAndSmooth } from '../lib/helpers';
import { UploadCloud, Trash2, XCircle, Loader2, Image, Sparkles, Files } from 'lucide-react';

// =============================
// IndexedDB (vanilla) helpers
// =============================
const DB_NAME = 'analyze-store-v1';
const STORE = 'items';

type IdxItem = {
  id: string;
  filename: string;
  mime: string;
  blob: Blob;           // preview용 이미지 Blob (원본 파일 저장)
  result: YoloAnalysisResult[] | null;
  avg_confidence?: number;
  coverMode?: boolean;
};

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbPut(item: IdxItem) {
  const db = await openDB();
  await new Promise<void>((res, rej) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
    tx.objectStore(STORE).put(item);
  });
}

async function idbBulkGet(ids: string[]): Promise<IdxItem[]> {
  const db = await openDB();
  return await new Promise((res) => {
    const tx = db.transaction(STORE, 'readonly');
    const store = tx.objectStore(STORE);
    const out: IdxItem[] = [];
    let remaining = ids.length;
    if (remaining === 0) return res([]);
    ids.forEach((id) => {
      const r = store.get(id);
      r.onsuccess = () => {
        if (r.result) out.push(r.result as IdxItem);
        if (--remaining === 0) res(out);
      };
      r.onerror = () => {
        if (--remaining === 0) res(out);
      };
    });
  });
}

async function idbDelete(id: string) {
  const db = await openDB();
  await new Promise<void>((res, rej) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
    tx.objectStore(STORE).delete(id);
  });
}

async function idbClear() {
  const db = await openDB();
  await new Promise<void>((res, rej) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
    tx.objectStore(STORE).clear();
  });
}

// =============================
// Types & utils
// =============================
interface AnalysisState {
  id: string;
  file: File | null; // 업로드 직후만 존재; 새로고침 복원 시 null
  previewUrl: string; // Object URL (마운트 때 Blob→ObjectURL로 생성)
  result: YoloAnalysisResult[] | null;
  error: string | null;
  isLoading: boolean;
  isSelected: boolean;
  avg_confidence?: number;
  coverMode?: boolean;
}

type WithFile = AnalysisState & { file: File };

type ServerSettings = {
  MAX_FILES: number;
  MAX_BYTES: number;
};

const normBase = (s?: string) => (s ? s.split('\\').pop()!.split('/').pop()! : '');

// =============================
// localStorage keys
// =============================
const LS_KEYS = {
  order: 'analyze_strip_order', // string[] of ids (보여줄 순서)
  activeId: 'analyze_active_id',
  mainViewerUrl: 'analyze_main_viewer_url',
  lastVideoRel: 'analyze_last_video_rel',
} as const;

// =============================
// Component
// =============================
export default function Analyze() {
  const [analysisStates, setAnalysisStates] = useState<AnalysisState[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [mainViewerUrl, setMainViewerUrl] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const [serverSettings, setServerSettings] = useState<ServerSettings | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const hasSelectedItems = analysisStates.some((s) => s.isSelected);
  const selected = useMemo(() => analysisStates.find((s) => s.id === activeId) || null, [analysisStates, activeId]);
  const hasDetectionsInSelected = (selected?.result?.length ?? 0) > 0;

  const isVideo = !!videoUrl;
  const [viewSize] = useState<{ w: number; h: number } | null>(null);
  const leftColRef = useRef<HTMLDivElement | null>(null);
  const [leftColH] = useState(0);
  const imgWrapRef = useRef<HTMLDivElement | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgOverlay, setImgOverlay] = useState<{ offX: number; offY: number; drawW: number; drawH: number } | null>(null);
  const VIEWER_ZOOM = 0.94;

  // =============================
  // Overlay calc (unchanged)
  // =============================
  const calcOverlay = useCallback(() => {
    const wrap = imgWrapRef.current,
      img = imgRef.current;
    if (!wrap || !img) return;

    const wrapW = wrap.clientWidth || 1;
    const wrapH = wrap.clientHeight || 1;

    const iw = img.naturalWidth || 1;
    const ih = img.naturalHeight || 1;

    const s = Math.min(wrapW / iw, wrapH / ih);

    const dW0 = Math.round(iw * s);
    const dH0 = Math.round(ih * s);

    const drawW = Math.round(dW0 * VIEWER_ZOOM);
    const drawH = Math.round(dH0 * VIEWER_ZOOM);

    const offX = Math.floor((wrapW - drawW) / 2);
    const offY = Math.floor((wrapH - drawH) / 2);

    setImgOverlay({ drawW, drawH, offX, offY });
  }, []);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  // 서버 설정 불러오기
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get<ServerSettings>('/settings/');
        setServerSettings(data);
      } catch {}
    })();
  }, []);

  // =============================
  // Boot: 복원(IndexedDB + localStorage)
  // =============================
  useEffect(() => {
    (async () => {
      try {
        const orderRaw = localStorage.getItem(LS_KEYS.order);
        const ids: string[] = orderRaw ? JSON.parse(orderRaw) : [];
        const savedActive = localStorage.getItem(LS_KEYS.activeId);
        const savedViewer = localStorage.getItem(LS_KEYS.mainViewerUrl);
        const savedRel = localStorage.getItem(LS_KEYS.lastVideoRel);

        // 1) 이미지 스트립 복원
        const items = await idbBulkGet(ids);
        // map: id -> ObjectURL
        const urlMap = new Map<string, string>();
        items.forEach((it) => {
          const url = URL.createObjectURL(it.blob);
          urlMap.set(it.id, url);
        });

        const restored: AnalysisState[] = ids
          .map((id) => items.find((it) => it.id === id))
          .filter(Boolean)
          .map((it) => ({
            id: it!.id,
            file: null, // 새로고침 후에는 File 없음
            previewUrl: urlMap.get(it!.id)!,
            result: it!.result ?? null,
            error: null,
            isLoading: false,
            isSelected: false,
            avg_confidence: it!.avg_confidence,
            coverMode: it!.coverMode ?? false,
          }));

        setAnalysisStates(restored);

        // 2) 비디오 복원
        if (savedRel) {
          const absolute = api.getUri({ url: savedRel });
          const withTs = `${absolute}?t=${Date.now()}`;
          setVideoUrl(withTs);
          // 뷰어가 비디오를 가리키고 있었다면 유지
          const isViewerVideo = savedViewer && savedRel && savedViewer.includes(savedRel);
          if (isViewerVideo) setMainViewerUrl(withTs);
          setTaskStatus('이전 동영상 분석 결과를 불러왔습니다.');
        }

        // 3) 뷰어/액티브 복원
        setActiveId(savedActive ?? (ids.length ? ids[0] : null));
        setMainViewerUrl((prev) => prev ?? (savedViewer || (restored[0]?.previewUrl ?? null)));
      } catch (e) {
        console.warn('복원 실패', e);
      }
    })();

    // cross-tab 동기화: 다른 탭에서 수정되면 재로드
    const onStorage = (ev: StorageEvent) => {
      if (!ev.key) return;
      if (ev.key === LS_KEYS.order || ev.key === LS_KEYS.activeId || ev.key === LS_KEYS.mainViewerUrl || ev.key === LS_KEYS.lastVideoRel) {
        // 간단히 전체를 재복원
        location.reload();
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  // 상태 변화 시 메타 보존
  useEffect(() => {
    localStorage.setItem(LS_KEYS.activeId, activeId ?? '');
  }, [activeId]);

  useEffect(() => {
    if (mainViewerUrl) localStorage.setItem(LS_KEYS.mainViewerUrl, mainViewerUrl);
  }, [mainViewerUrl]);

  useEffect(() => {
    const order = analysisStates.map((s) => s.id);
    localStorage.setItem(LS_KEYS.order, JSON.stringify(order));
  }, [analysisStates]);

  // 새로고침(탭 닫기 포함) 보호: 분석 중일 때만 경고
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
    const roImg = new ResizeObserver(() => calcOverlay());

    if (imgWrapRef.current) roWrap.observe(imgWrapRef.current);
    if (imgRef.current) roImg.observe(imgRef.current);

    const onLoad = () => requestAnimationFrame(calcOverlay);
    imgRef.current?.addEventListener('load', onLoad);
    window.addEventListener('resize', calcOverlay);
    requestAnimationFrame(calcOverlay);

    return () => {
      roWrap.disconnect();
      roImg.disconnect();
      window.removeEventListener('resize', calcOverlay);
      imgRef.current?.removeEventListener('load', onLoad);
    };
  }, [calcOverlay]);

  useEffect(() => {
    calcOverlay();
  }, [calcOverlay, mainViewerUrl, selected?.result, selected?.coverMode, leftColH]);

  const [smoothDets, setSmoothDets] = useState<any[]>([]);
  useEffect(() => {
    const raw = (selected?.result ?? []).map((d: any) => {
      const b = d.boundingBox;
      return {
        title: d.label ?? d.ripeness ?? d.className ?? d.class ?? '',
        conf: d.confidence ?? 0,
        x: b.x,
        y: b.y,
        w: b.width,
        h: b.height,
      };
    });
    setSmoothDets((prev) => matchAndSmooth(prev, raw, 0.25));
  }, [selected?.result]);

  // =============================
  // Drop: 파일을 IndexedDB에 저장 + 상태 반영
  // =============================
  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const filtered = acceptedFiles.filter((f) => f.size > 0 && f.type.startsWith('image/'));
    if (filtered.length === 0) {
      setTaskStatus('이미지를 추가해 주세요.');
      return;
    }

    const newStates: AnalysisState[] = [];
    for (const file of filtered) {
      const id = `${file.name}-${file.lastModified}-${Math.random()}`;
      // 저장: 원본 File을 그대로 Blob으로 보관 → 복원 시 ObjectURL 재생성
      const item: IdxItem = {
        id,
        filename: file.name,
        mime: file.type || 'image/*',
        blob: file,
        result: null,
      };
      await idbPut(item);

      const previewUrl = URL.createObjectURL(file);
      newStates.push({
        id,
        file,
        previewUrl,
        result: null,
        error: null,
        isLoading: false,
        isSelected: false,
        avg_confidence: undefined,
        coverMode: false,
      });
    }

    setVideoUrl(null);
    setTaskStatus(null);
    localStorage.removeItem(LS_KEYS.lastVideoRel);

    setAnalysisStates((prev) => {
      const combined = [...prev, ...newStates];
      if (!mainViewerUrl || prev.length === 0) setMainViewerUrl(newStates[0].previewUrl);
      if (!activeId && prev.length === 0) setActiveId(newStates[0].id);
      // 순서 보존
      const order = combined.map((s) => s.id);
      localStorage.setItem(LS_KEYS.order, JSON.stringify(order));
      return combined;
    });
  }, [mainViewerUrl, activeId]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.jpeg', '.png', '.jpg', '.webp'] },
    multiple: true,
  });

  // =============================
  // 분석 실행
  // =============================
  const handleAnalyze = async () => {
    const targets = analysisStates.filter((s): s is WithFile => !!s.file && s.file.size > 0 && !s.result && !s.error);
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

  const updatePersistedItemMeta = async (id: string, patch: Partial<IdxItem>) => {
    // 현재 저장된 blob/meta를 읽어와 patch 적용
    const [item] = await idbBulkGet([id]);
    if (!item) return;
    await idbPut({ ...item, ...patch });
  };

  const analyzeSingleImage = async (targetState: WithFile) => {
    setActiveId(targetState.id);
    setMainViewerUrl(targetState.previewUrl);
    setAnalysisStates((prev) => prev.map((s) => (s.id === targetState.id ? { ...s, isLoading: true, error: null } : s)));
    try {
      const base64Image = await fileToBase64(targetState.file);
      const res = await api.post<ImageAnalysisResultPayload>(`/analysis/analyze`, { image: base64Image }, { timeout: 60000 });
      const { detections, avg_confidence } = res.data;
      const formattedDetections = detections.map((d) => ({ ...d, label: d.ripeness }));
      setAnalysisStates((prev) =>
        prev.map((s) =>
          s.id === targetState.id
            ? { ...s, result: formattedDetections, avg_confidence: avg_confidence ?? 0, isLoading: false, coverMode: false }
            : s
        )
      );
      // IndexedDB 메타에도 반영
      await updatePersistedItemMeta(targetState.id, { result: formattedDetections as any, avg_confidence: avg_confidence ?? 0 });
    } catch (err: any) {
      const msg = err.response?.data?.detail || (err.code === 'ECONNABORTED' ? '요청 시간이 초과되었습니다. 잠시 후 다시 시도하세요.' : '분석 실패');
      setAnalysisStates((prev) => prev.map((s) => (s.id === targetState.id ? { ...s, error: msg, isLoading: false } : s)));
    }
  };

  const analyzeMultipleImagesAsVideo = (statesToAnalyze: WithFile[]): Promise<void> =>
    new Promise<void>(async (resolve, reject) => {
      setTaskStatus('이미지 분석 및 동영상 생성 요청 중...');
      const idsToAnalyze = new Set(statesToAnalyze.map((s) => s.id));
      setAnalysisStates((prev) => prev.map((s) => (idsToAnalyze.has(s.id) ? { ...s, isLoading: true, error: null } : s)));
      try {
        const formData = new FormData();
        statesToAnalyze.forEach((s) => {
          if (s.file) formData.append('files', s.file);
        });
        const res = await api.post<{ task_id: string; results: ImageAnalysisResultPayload[] }>(`/analysis/analyze_video`, formData, { timeout: 120000 });
        const { task_id, results } = res.data;
        const norm = (s: string) => s.split('\\').pop()!.split('/').pop()!;
        const resultsMap = new Map(results.map((r) => [norm(r.filename), r]));

        setAnalysisStates((prev) => {
          const next = prev.map((s) => {
            const key = s.file ? norm(s.file.name) : undefined;
            const match = key ? resultsMap.get(key) : undefined;
            return match
              ? {
                  ...s,
                  result: match.detections.map((d) => ({ ...d, label: d.ripeness })),
                  avg_confidence: match.avg_confidence ?? 0,
                  isLoading: false,
                  error: null,
                }
              : s;
          });
          return next;
        });
        // 메타 동기화(IndexedDB)
        for (const s of statesToAnalyze) {
          const m = resultsMap.get(norm(s.file.name));
          if (m) await updatePersistedItemMeta(s.id, { result: m.detections as any, avg_confidence: m.avg_confidence ?? 0 });
        }

        setTaskStatus('동영상 생성 중...');
        setMainViewerUrl(null);
        setActiveId(null);
        pollRef.current = window.setInterval(async () => {
          try {
            const { data } = await api.get(`/tasks/${task_id}/status`, { params: { ts: Date.now() }, timeout: 60000 });
            if (Array.isArray(data.image_results) && data.image_results.length > 0) {
              setAnalysisStates((prev) => mergeServerImageResults(prev, data.image_results, idsToAnalyze));
              const done = data.image_results.filter((r: any) => r?.processed === true || r?.error).length;
              const total = statesToAnalyze.length;
              setTaskStatus(`분석 중... ${done}/${total}`);
            }
            if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
              if (pollRef.current) clearInterval(pollRef.current);
              pollRef.current = null;

              if (Array.isArray(data.image_results)) {
                setAnalysisStates((prev) => mergeServerImageResults(prev, data.image_results, idsToAnalyze));
              }
              setIsAnalyzing(false);

              if (data.status === 'SUCCESS') {
                const finalRel = data.result; // "/results/xxx.mp4"
                const absolute = data.absolute_result ?? api.getUri({ url: finalRel });
                const once = absolute + `?t=${Date.now()}`;
                setVideoUrl((prev) => prev ?? once);
                setMainViewerUrl((prev) => prev ?? once);
                localStorage.setItem(LS_KEYS.lastVideoRel, finalRel);
                setTaskStatus(null);
              } else {
                setTaskStatus('오류: 동영상 생성 실패');
              }
              resolve();
            }
          } catch (pollError) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setIsAnalyzing(false);
            setTaskStatus('상태 확인 중 오류');
            console.error(pollError);
          }
        }, 3000);
      } catch (reqError: any) {
        const msg = reqError.response?.data?.detail || (reqError.code === 'ECONNABORTED' ? '요청 시간이 초과되었습니다. 잠시 후 다시 시도하세요.' : '서버가 바쁘거나 일시적으로 중단되었습니다. 잠시 후 다시 시도하세요.');
        setTaskStatus(msg);
        setAnalysisStates((prev) => prev.map((s) => (idsToAnalyze.has(s.id) ? { ...s, isLoading: false, error: msg } : s)));
        setIsAnalyzing(false);
        reject(reqError);
      }
    });

  // 서버 image_results를 현재 analysisStates에 반영 + IndexedDB 메타 반영
  function mergeServerImageResults(prev: AnalysisState[], server: ImageAnalysisResultPayload[], idsToAnalyze?: Set<string>) {
    const map = new Map(server.map((r) => [normBase(r.filename), r]));
    const next = prev.map((s) => {
      if (idsToAnalyze && !idsToAnalyze.has(s.id)) return s;
      if (!s.file) return s; // 업로드 기반 매칭만 갱신
      const m = map.get(normBase(s.file.name));
      if (!m) return s;
      const dets = (m.detections ?? []).map((d) => ({ ...d, label: d.ripeness }));
      const finished = m.processed === true || Boolean(m.error);
      // IndexedDB 업데이트(비동기, 실패해도 UI는 유지)
      updatePersistedItemMeta(s.id, { result: dets as any, avg_confidence: m.avg_confidence ?? s.avg_confidence });
      return { ...s, result: dets, avg_confidence: m.avg_confidence ?? s.avg_confidence, error: m.error ?? null, isLoading: !finished };
    });
    return next;
  }

  // ==============
  // Actions
  // ==============
  const handleClearAll = async () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    // Object URL 해제
    analysisStates.forEach((s) => {
      try {
        if (s.previewUrl?.startsWith('blob:')) URL.revokeObjectURL(s.previewUrl);
      } catch {}
    });
    setAnalysisStates([]);
    setVideoUrl(null);
    setTaskStatus(null);
    setMainViewerUrl(null);
    await idbClear();
    localStorage.removeItem(LS_KEYS.order);
    localStorage.removeItem(LS_KEYS.lastVideoRel);
    localStorage.removeItem(LS_KEYS.activeId);
    localStorage.removeItem(LS_KEYS.mainViewerUrl);
  };

  const handleDeleteSelected = async () => {
    const toDelete = analysisStates.filter((s) => s.isSelected).map((s) => s.id);
    for (const id of toDelete) await idbDelete(id);

    setAnalysisStates((prev) => {
      const kept = prev.filter((s) => !toDelete.includes(s.id));
      kept.forEach(() => {
        /* keep */
      });
      const nextActive = kept.some((s) => s.id === activeId) ? activeId : kept[0]?.id ?? null;
      setActiveId(nextActive);
      setMainViewerUrl(nextActive ? kept.find((k) => k.id === nextActive)?.previewUrl ?? null : null);
      const order = kept.map((s) => s.id);
      localStorage.setItem(LS_KEYS.order, JSON.stringify(order));
      return kept;
    });
  };

  // ==============
  // Render
  // ==============
  const boxes = smoothDets.length
    ? smoothDets
    : (selected?.result ?? []).map((d: any) => ({
        title: d.label ?? d.ripeness ?? d.className ?? d.class ?? '',
        conf: d.confidence ?? 0,
        x: d.boundingBox?.x ?? 0,
        y: d.boundingBox?.y ?? 0,
        w: d.boundingBox?.width ?? 0,
        h: d.boundingBox?.height ?? 0,
      }));

  return (
    <div className="bg-slate-50 min-h-screen flex flex-col font-sans">
      {(isAnalyzing || !!pollRef.current) && (
        <div
          role="status"
          aria-live="polite"
          className="fixed top-3 left-1/2 -translate-x-1/2 z-50 bg-amber-50 text-amber-700 border border-amber-300 rounded-full px-4 py-2 shadow"
        >
          이미지 분석/동영상 생성 중입니다. 새로고침이나 탭 이동을 피해주세요.
        </div>
      )}

      <main className="flex-grow grid grid-cols-1 lg:grid-cols-12 gap-6 p-4 sm:p-6">
        <div ref={leftColRef} className="lg:col-span-8 xl:col-span-9 flex flex-col gap-6">
          {/* 미디어 뷰어 */}
          <motion.div
            layout
            className={
              'bg-white rounded-2xl shadow-lg flex items-center justify-center relative overflow-hidden p-2 ' +
              (hasDetectionsInSelected ? 'min-h-[320px] sm:min-h-[420px] md:min-h-[560px]' : 'min-h-[320px] sm:min-h-[480px] md:min-h-[600px]')
            }
          >
            <AnimatePresence>
              {!mainViewerUrl && (
                <motion.div key="placeholder" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }} className="text-center text-slate-400">
                  <Image className="w-20 h-20 mb-4 mx-auto" />
                  <h2 className="text-xl font-bold text-slate-600">미디어 뷰어</h2>
                  <p className="text-slate-500">이미지를 선택하거나 결과를 확인하세요.</p>
                </motion.div>
              )}
            </AnimatePresence>

            {/* 이미지/비디오 뷰어 */}
            {mainViewerUrl && (mainViewerUrl === videoUrl ? (
              <div className="w-full max-w-full rounded-lg overflow-hidden bg-black" style={{ aspectRatio: isVideo ? '16 / 9' : viewSize ? `${viewSize.w} / ${viewSize.h}` : '4 / 3' }}>
                <video
                  key={videoUrl || ''}
                  src={videoUrl || undefined}
                  controls
                  playsInline
                  preload="metadata"
                  autoPlay={false}
                  loop={false}
                  muted
                  className="w-full h-full object-contain rounded-lg bg-black"
                  onEnded={(e) => {
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
              <div ref={imgWrapRef} className="relative w-full h-[320px] sm:h-[360px] md:h-[420px] flex justify-center items-center">
                <img ref={imgRef} src={mainViewerUrl} alt="Main view" className="w-full h-full object-contain rounded-lg" onLoad={calcOverlay} />
                {imgOverlay && selected?.result?.length ? (
                  <div
                    className="absolute pointer-events-none overflow-hidden z-10"
                    style={{ left: imgOverlay.offX, top: imgOverlay.offY, width: imgOverlay.drawW, height: imgOverlay.drawH }}
                  >
                    <div className="absolute inset-0">
                      {boxes.map((det: any, i: number) => {
                        const { drawW, drawH } = imgOverlay;
                        const b = det?.boundingBox || {};
                        const nx = Math.max(0, Math.min(1, Number(b.x) || 0));
                        const ny = Math.max(0, Math.min(1, Number(b.y) || 0));
                        const nw = Math.max(0, Math.min(1 - nx, Number(b.width) || 0));
                        const nh = Math.max(0, Math.min(1 - ny, Number(b.height) || 0));

                        let x1 = nx * drawW,
                          y1 = ny * drawH;
                        let x2 = (nx + nw) * drawW,
                          y2 = (ny + nh) * drawH;

                        x1 = Math.max(0, Math.min(drawW - 1, x1));
                        y1 = Math.max(0, Math.min(drawH - 1, y1));
                        x2 = Math.max(x1 + 1, Math.min(drawW, x2));
                        y2 = Math.max(y1 + 1, Math.min(drawH, y2));

                        const x = Math.round(x1),
                          y = Math.round(y1);
                        const w = Math.round(x2 - x1),
                          h = Math.round(y2 - y1);

                        const title = det.label ?? det.ripeness ?? det.className ?? det.class ?? '';
                        const LABEL_H = 18;
                        const labelTop = y - LABEL_H >= 0 ? -LABEL_H : 0;

                        return (
                          <div key={i} style={{ position: 'absolute', left: x, top: y, width: w, height: h, border: '3px solid #FACC15', borderRadius: 2, boxSizing: 'border-box', overflow: 'visible', zIndex: 10 + i }}>
                            <div className="absolute bg-black/80 text-white text-xs px-1.5 rounded" style={{ left: 0, top: labelTop, maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              {title} {Number(det.confidence * 100).toFixed(1)}%
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
            ))}

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
              <h3 className="text-sm sm:text-md font-bold text-slate-700">이미지 스트립 ({analysisStates.length})</h3>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-slate-200 hover:scrollbar-thumb-slate-300 scrollbar-track-slate-50">
              {analysisStates.map((state) => (
                <div
                  key={state.id}
                  onClick={() => {
                    if (isAnalyzing) return;
                    setActiveId(state.id);
                    setMainViewerUrl(state.previewUrl);
                  }}
                  className={`relative flex-shrink-0 w-36 h-40 sm:w-40 sm:h-44 md:w-44 md:h-48 rounded-xl overflow-hidden cursor-pointer group border-2 ${
                    mainViewerUrl === state.previewUrl ? 'border-indigo-500' : 'border-transparent hover:border-indigo-300'
                  }`}
                >
                  <div className="absolute top-1 left-1 z-10" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={state.isSelected}
                      onChange={(e) => {
                        e.stopPropagation();
                        setAnalysisStates((prev) => prev.map((s) => (s.id === state.id ? { ...s, isSelected: !s.isSelected } : s)));
                      }}
                      className="w-4 h-4 accent-indigo-600"
                      aria-label="선택"
                    />
                  </div>
                  <div className="relative w-full h-full overflow-visible">
                    <img src={state.previewUrl} alt="preview" className="w-full h-full object-cover" />
                    {state.result?.map((det, i) => {
                      const b = det.boundingBox;
                      const x = Math.max(0, Math.min(1, b.x));
                      const y = Math.max(0, Math.min(1, b.y));
                      const w = Math.max(0, Math.min(1 - x, b.width));
                      const h = Math.max(0, Math.min(1 - y, b.height));
                      return (
                        <div key={i} className="absolute border-[3px] md:border-4 border-yellow-400 rounded-sm" style={{ left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` }}>
                          <div className="absolute bg-black/80 text-white text-[10px] sm:text-xs px-1.5 rounded font-semibold whitespace-nowrap" style={{ left: 0, top: Math.max(0, -1 + 0) }}>
                            {det.ripeness} {Number((det.confidence * 100).toFixed(1))}%
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  {state.error && <div className="absolute inset-0 bg-red-700/80 text-xs text-white font-bold flex items-center justify-center">{state.error}</div>}
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
        <aside className="lg:col-span-4 xl:col-span-3 bg-white rounded-2xl shadow-lg p-4 sm:p-6 flex flex-col sticky top-6 overflow-auto max-h-[calc(100vh-1.5rem)]">
          <h2 className="text-lg sm:text-2xl font-bold text-slate-900 mb-3">제어판</h2>
          <div
            {...getRootProps()}
            className={`flex-1 min-h-[300px] sm:min-h-[360px] lg:min-h-[420px] border-2 border-dashed rounded-xl p-6 w-full text-center flex flex-col justify-center items-center cursor-pointer transition-all duration-300 ${
              isDragActive ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 hover:border-indigo-400'
            }`}
          >
            <input {...getInputProps()} />
            <UploadCloud className="w-12 h-12 mx-auto mb-2 text-slate-400" />
            <p className="font-semibold text-slate-700">클릭 또는 드래그하여 파일 추가</p>
            <p className="text-xs text-slate-500 mt-1">PNG, JPG, WEBP 지원</p>
            {serverSettings && (
              <p className="text-[11px] text-slate-400 mt-1">
                서버 제한:&nbsp;
                {serverSettings.MAX_FILES === 0 ? '개수 무제한' : `최대 ${serverSettings.MAX_FILES}장`},&nbsp;
                {serverSettings.MAX_BYTES === 0 ? '용량 무제한' : `파일당 ${(serverSettings.MAX_BYTES / (1024 * 1024)).toFixed(1)} MB`}
              </p>
            )}
          </div>

          {analysisStates.length > 0 && (
            <div className="mt-6 space-y-4">
              <motion.button whileTap={{ scale: 0.98 }} onClick={handleAnalyze} disabled={isAnalyzing} className="w-full flex items-center justify-center gap-2 text-base px-4 py-2 bg-indigo-600 text-white font-bold rounded-lg hover:bg-indigo-700 disabled:bg-slate-400 transition-all">
                {isAnalyzing ? <Loader2 className="animate-spin" /> : <Sparkles />}
                분석 실행
              </motion.button>
              <div className="grid grid-cols-2 gap-4">
                <button onClick={handleDeleteSelected} disabled={isAnalyzing || !hasSelectedItems} className="flex items-center justify-center gap-2 px-3 py-2 bg-slate-200 text-slate-700 text-sm font-semibold rounded-lg hover:bg-slate-300 disabled:bg-slate-100">
                  <Trash2 size={14} />
                  선택 삭제
                </button>
                <button onClick={handleClearAll} disabled={isAnalyzing} className="flex items-center justify-center gap-2 px-3 py-2 bg-rose-100 text-rose-600 text-sm font-semibold rounded-lg hover:bg-rose-200 disabled:bg-rose-50 disabled:text-rose-300">
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

// =============================
// 기존 유틸: 파일→Base64 (단일 이미지 분석용)
// =============================
const fileToBase64 = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const result = reader.result as string;
      if (!result || !result.includes(',')) reject('Base64 변환 실패');
      else resolve(result.split(',')[1]);
    };
    reader.onerror = (error) => reject(error);
  });
