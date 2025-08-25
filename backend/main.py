# --- 📁 backend/main.py ---

import os, asyncio, concurrent.futures, base64, uuid, threading, json, smtplib, pytz, cv2, torch, subprocess, shutil, numpy as np
from datetime import datetime, timedelta, date, time as dtime
from pytz import timezone
from pathlib import Path
from markupsafe import Markup
from io import BytesIO
from PIL import Image, ImageOps, ImageFont, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True # 손상/부분 이미지도 최대한 로드
from dotenv import load_dotenv
load_dotenv()

from collections import Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# FastAPI 및 관련 라이브러리
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Request, status, Header, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.security import OAuth2PasswordRequestForm
from typing import List, Tuple, Dict

# 인증 관련 라이브러리
from jose import jwt, JWTError
from passlib.context import CryptContext

# SQLAlchemy 관련 import 문 추가
from sqlalchemy import func
from sqlalchemy.orm import Session


# SQLAdmin 관련 import 문 추가
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend

# Pydantic 및 YOLO
from pydantic import BaseModel
from ultralytics import YOLO

# 로컬 DB 및 모델 초기화
from db import engine, SessionLocal, init_db
from models import User, Analysis, DailyAnalysisStat, TaskStatus, DailyBoxCount

# --- 한국 시간 설정 ---
KST = pytz.timezone("Asia/Seoul")

# --- 🔐 인증 및 암호화 설정 ---
SECRET_KEY = '482a2ca94b3c91eeb219221cb86decb51d1969a9fe3accb8e547909907ccd932'
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed):
    return pwd_context.verify(plain_password, hashed)

# --- 🗄️ DB 설정 ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- 📦 Pydantic 모델 ---
class UserCreate(BaseModel):
    nickname: str
    email: str
    password: str
    password_confirm: str

class Token(BaseModel):
    access_token: str
    token_type: str

class ImagePayload(BaseModel):
    image: str  # base64 인코딩된 이미지 문자열

class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float

class YoloAnalysisResult(BaseModel):
    ripeness: str
    confidence: float
    boundingBox: BoundingBox

class StatsResponse(BaseModel):
    todayAnalyses: int
    avgRipeness: float
    totalUploads: int

class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.nickname, User.email]

class AnalysisAdmin(ModelView, model=Analysis):
    name = "분석 기록"
    name_plural = "분석 기록"
    icon = "fa-solid fa-video"
    column_list = [Analysis.id, Analysis.username, Analysis.ripeness,
                Analysis.confidence, Analysis.created_at, "preview"]

    # 🔹 Admin 테이블에 썸네일 / 동영상 미리보기 칼럼
    async def preview(self, obj):
        preview_html = ""

        # 이미지 썸네일
        if obj.image_path:
            preview_html += f"<img src='/results/{obj.image_path}' width='80' style='margin:3px; border-radius:6px;'>"

        # 동영상 미리보기 버튼
        if obj.video_path:
            preview_html += f"""
                <video width='120' controls style='margin:3px;'>
                    <source src='{obj.video_path}' type='video/mp4'>
                    Your browser does not support the video tag.
                </video>
            """

        return Markup(preview_html) if preview_html else "-"

    column_formatters = {
        "preview": preview
    }

    # ✅ 기본 CRUD 허용 (추가, 수정, 삭제)
    can_create = True
    can_edit = True
    can_delete = True

    # ✅ 새 레코드 추가 시 필드 지정
    form_columns = [
        "username", "ripeness", "confidence", "image_path", "video_path", "created_at"
    ]

class SimpleAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = form.get("username")
        password = form.get("password")

        db = SessionLocal()
        user = db.query(User).filter(User.email == email).first()
        db.close()

        if user and verify_password(password, user.password_hash) and user.is_superuser:
            token = jwt.encode({"sub": user.email}, SECRET_KEY, algorithm=ALGORITHM)
            request.session["token"] = token
            return True
        
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        if not token:
            return False

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
            db = SessionLocal()
            user = db.query(User).filter(User.email == email).first()
            db.close()

            return bool(user and user.is_superuser)
        except JWTError:
            return False 
        
# --- 🧠 FastAPI 앱 생성 ---
app = FastAPI(title="바나나 YOLO 분석")

admin = Admin(app, engine, authentication_backend=SimpleAuth(secret_key=SECRET_KEY))
admin.add_view(UserAdmin)
admin.add_view(AnalysisAdmin)

# --- CORS 설정 ---
FRONT_FIXED = [
    "http://localhost:5173",
    "https://classification-banana-frontend.onrender.com",
    "https://classification-banana.onrender.com",
    "https://classification-banana-2.onrender.com",
]

FRONT_REGEX = r"^https://classification-banana(?:-[a-z0-9]+)?\.onrender\.com$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONT_FIXED,          # 고정값 우선 매치
    allow_origin_regex=FRONT_REGEX,     # 변형 서브도메인 폭넓게 허용
    allow_credentials=False,            # 쿠키 기반 인증 안 쓰면 False
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Cache-Control", "Content-Disposition"],
    max_age=86400,
)

# ✅ 세션 쿠키 보안 옵션 (SQLAdmin용)
https_only = os.getenv("ENV", "prod") == "prod"
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=https_only,
    same_site="lax",
    max_age=60 * 60 * 8,
)

# ✅ 결과 폴더
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# 작업 폴더
TASKS_DIR = (RESULTS_DIR / "tasks")
TASKS_DIR.mkdir(parents=True, exist_ok=True)

# --- 라우터 생성 ---
auth_router = APIRouter(tags=["Authentication"])
analysis_router = APIRouter(tags=["Analysis"])
task_router = APIRouter(tags=["Tasks"])
stats_router = APIRouter(tags=["Statistics"])
settings_router = APIRouter(tags=["Settings"])

# --- DB 세션 종속성 ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def set_task_db(db, task_id: str, **fields):
    row = db.get(TaskStatus, task_id) 
    if row is None:
        row = TaskStatus(id=task_id, status=fields.get("status","PENDING"))
        db.add(row)
    if "status" in fields: row.status = fields["status"]
    if "result" in fields: row.result = fields["result"]
    if "image_results" in fields:
        row.image_results = json.dumps(fields["image_results"])
    db.commit()

def get_task_db(db, task_id: str):
    row = db.get(TaskStatus, task_id)
    if not row: return None
    return {
        "id": row.id,
        "status": row.status,
        "result": row.result,
        "image_results": json.loads(row.image_results or "[]"),
        "updated_at": row.updated_at,
    }

# --- 절대 경로 설정 ---
BASE_DIR = Path(__file__).resolve().parent

# CPU 코어 수
CPU_CORES = max(1, os.cpu_count() or 1)

# YOLO/OpenCV 스레드 수
cv2.setNumThreads(1 if CPU_CORES <= 2 else 2)
torch.set_num_threads(1 if CPU_CORES <= 2 else 2)

# 추론용 스레드풀
EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1 if CPU_CORES <= 2 else 2
)

# 배치 추론(파일 여러 장 한 번에). CPU 1~2코어면 2, 4코어면 4 권장
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "2"))

# 프리프로세스 스레드(디코드/리사이즈). CPU 코어에 따라 1~2 권장
PREPROC_THREADS = 1 if CPU_CORES <= 2 else 2

# 해상도 일관화(모델/전처리/비디오 공통)
MODEL_W = int(os.getenv("MODEL_W", "640"))
MODEL_H = int(os.getenv("MODEL_H", "480"))
TARGET_W = int(os.getenv("TARGET_W", str(MODEL_W)))  # 비디오/표시 해상도
TARGET_H = int(os.getenv("TARGET_H", str(MODEL_H)))

# 업로드 제한(환경변수로 크게 조정 가능)
MAX_FILES = int(os.getenv("MAX_FILES", "15"))                 # 프론트는 제한 제거(아래 4번), 서버는 안전빵
MAX_BYTES = int(os.getenv("MAX_BYTES", str(8*1024*1024)))    # 10MB/파일

#  비디오 생성(멀티 이미지) 최적화 + 해상도 키우기
INFER_EVERY_N_FRAMES = int(os.getenv("INFER_EVERY_N_FRAMES", "10"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "8"))
USE_FFMPEG = os.getenv("USE_FFMPEG", "1") == "1"

# 감지 파라미터
FINAL_CONF  = float(os.getenv("FINAL_CONF",  "0.10"))
MAX_DET     = int(os.getenv("MAX_DET",      "3"))

# --- YOLO 로드 ---
MODEL_PATH = BASE_DIR / "best.pt"

# 3-1) 전역 상태
model = None
MODEL_READY = False
DB_READY = False


os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("MALLOC_ARENA_MAX", "2")
os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")

# 스레드 수 강제
try:
    import cv2
    cv2.setNumThreads(1)
except Exception:
    pass

try:
    import torch
    torch.set_num_threads(1)      # PyTorch 내부 스레드
    torch.set_num_interop_threads(1)
except Exception:
    pass

# 3-2) 무거운 초기화 함수
def _heavy_init():
    global model, MODEL_READY, DB_READY

    # ── 0) DB 준비
    try:
        init_db()
        DB_READY = True
        print("✅ DB init done")
    except Exception as e:
        print("❌ DB init failed:", e)

    # ── 1) CPU 환경 튜닝(선택) : 스레드 수/BLAS 제한으로 안정성+속도 균형
    try:
        # 기본값 과하면 컨테이너에서 문맥 전환 오버헤드 ↑
        cpu_cores = os.cpu_count() or 2
        omp_threads = int(os.getenv("OMP_NUM_THREADS", str(min(4, cpu_cores))))
        mkl_threads = int(os.getenv("MKL_NUM_THREADS", str(min(4, cpu_cores))))
        os.environ.setdefault("OMP_NUM_THREADS", str(omp_threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(mkl_threads))

        # OpenCV 스레드 제한
        try:
            import cv2
            cv2.setNumThreads(omp_threads)
        except Exception:
            pass

        # PyTorch 스레드 제한
        try:
            import torch
            torch.set_num_threads(omp_threads)
            torch.set_num_interop_threads(max(1, omp_threads // 2))
        except Exception:
            pass

        print(f"🧠 Threads -> OMP:{os.environ.get('OMP_NUM_THREADS')} MKL:{os.environ.get('MKL_NUM_THREADS')}")
    except Exception as e:
        print("⚠️ thread/env tuning skipped:", e)

    # ── 2) YOLO (PyTorch .pt) 로드: CPU 고정
    try:
        print(f"🔃 Loading PyTorch (CPU): {MODEL_PATH}")
        m = YOLO(MODEL_PATH)  # .pt

        # 약간의 CPU 최적화
        try:
            m.fuse()  # 일부 모델에서 Conv+BN fusion
        except Exception:
            pass

        # CPU 고정 (Render 무료 플랜)
        try:
            m.to("cpu")
        except Exception:
            pass

        # 공통 파라미터
        m.overrides.update({
            "conf": FINAL_CONF,
            "imgsz": (MODEL_W, MODEL_H),   # (W,H) 헷갈리지 않게 고정
            "max_det": MAX_DET,
            "agnostic_nms": True,
            "workers": 0,                  # DataLoader 안 씀
            "stream_buffer": False
        })

        globals()["model"] = m
        MODEL_READY = True
        print("✅ YOLO loaded: PyTorch (CPU)")
    except Exception as e:
        print("❌ YOLO load failed:", e)

    # ── 3) 일일 통계 초기 업데이트 (best-effort)
    try:
        db = SessionLocal()
        update_daily_analysis_stat(db, datetime.now(KST).date())
    except Exception as e:
        print("❌ update_daily_analysis_stat at startup:", e)
    finally:
        try:
            db.close()
        except:
            pass

# 3-3) 스타트업에서 비동기 시작
@app.on_event("startup")
def startup():
    threading.Thread(target=_heavy_init, daemon=True).start()

# 3-4) 핑 체크 (상태 정보 포함)
@app.get("/ping")
def ping():
    return {"ok": True, "model": MODEL_READY, "db": DB_READY}

@app.head("/ping", include_in_schema=False)
def ping_head():
    return Response(status_code=204, headers={"Cache-Control": "no-store"})

@app.get("/healthz", include_in_schema=False)
def healthz_get():
    return Response(status_code=204, headers={"Cache-Control": "no-store"})

@app.head("/healthz", include_in_schema=False)
def healthz_head():
    return Response(status_code=204, headers={"Cache-Control": "no-store"})

# Access 로그 필터링
import logging
logger = logging.getLogger("uvicorn.access")

class _SkipNoise(logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        # 헬스체크 전부 + HEAD /ping 은 숨기고, GET /ping 은 남김(원하면 지우세요)
        if '"/healthz' in msg:
            return False
        if '"HEAD /ping' in msg:
            return False
        return True

logger.addFilter(_SkipNoise())

KOREAN_CLASSES = {
    "freshripe": "신선한 완숙",
    "freshunripe": "신선한 미숙",
    "overripe": "과숙",
    "ripe": "완숙",
    "rotten": "썩음",
    "unripe": "미숙"
}

LABEL_SCORE = {
    "미숙": 20,
    "신선한 미숙": 40,
    "완숙": 60,
    "신선한 완숙": 80,
    "과숙": 60,
    "썩음": 20
}

FRESHNESS_MAP = {
    "freshripe": 1.0,
    "freshunripe": 0.9,
    "ripe": 0.8,
    "unripe": 0.6,
    "overripe": 0.3,
    "rotten": 0.0,
}

# 한글 폰트 경로: 환경변수 우선, 없으면 프로젝트 상대 경로
FONT_PATH = os.getenv(
    "FONT_PATH",
    str((Path(__file__).parent / "fonts" / "NanumGothic.ttf").resolve())
)
_font_cache = {}

def _get_font(size: int = 24):
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype(FONT_PATH, size=size)
        except Exception:
            _font_cache[size] = ImageFont.load_default()  # (한글 미지원일 수 있음)
    return _font_cache[size]

# --- YOLO 분석 함수 (여러 객체 지원) ---
def letterbox_image(img, target_width, target_height):
    h, w = img.shape[:2]
    scale = min(target_width / w, target_height / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (nw, nh))
    new_img = np.full((target_height, target_width, 3), 128, dtype=np.uint8)
    top = (target_height - nh) // 2
    left = (target_width - nw) // 2
    new_img[top:top+nh, left:left+nw] = resized
    return new_img

def run_yolo_np_bgr(imgs_bgr, imgsz=None, conf=None, max_det=None):
    if not model:
        raise HTTPException(status_code=503, detail="모델을 사용할 수 없습니다.")

    single_input = isinstance(imgs_bgr, np.ndarray)
    imgs = [imgs_bgr] if single_input else list(imgs_bgr)
    if not imgs:
        return [] if single_input else []

    if isinstance(imgsz, (list, tuple)) and len(imgsz) == 2:
        sz = tuple(imgsz)
    else:
        sz = (MODEL_W, MODEL_H,)
    res_list = model(imgs, imgsz=sz, conf=(conf or 0.1),
                     max_det=(max_det or 100), device='cpu', verbose=False)

    VALID = {"ripe","unripe","freshripe","freshunripe","overripe","rotten"}
    outputs = []

    for img_bgr, res in zip(imgs, res_list):
        h, w = img_bgr.shape[:2]
        dets = []
        for box in (res.boxes or []):
            cls = model.names[int(box.cls.item())]
            if cls not in VALID:
                continue

            # xyxy → 정규화(0~1). 음수/초과 값 보정
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            # 음수/초과 보정 (모델/리사이즈 경계 오차)
            x1 = max(0.0, min(w - 1.0, x1))
            y1 = max(0.0, min(h - 1.0, y1))
            x2 = max(0.0, min(w - 1.0, x2))
            y2 = max(0.0, min(h - 1.0, y2))
            if x2 <= x1: x2 = min(w - 1.0, x1 + 1.0)
            if y2 <= y1: y2 = min(h - 1.0, y1 + 1.0)

            nx = x1 / w
            ny = y1 / h
            nw = (x2 - x1) / w
            nh = (y2 - y1) / h

            # 우/하단 미세 넘침 보정(부동소수점 안전 마진)
            eps = 1e-4
            if nx + nw > 1.0: nw = max(0.0, 1.0 - nx - eps)
            if ny + nh > 1.0: nh = max(0.0, 1.0 - ny - eps)

            dets.append({
                "ripeness": KOREAN_CLASSES.get(cls, cls),
                "confidence": float(box.conf.item()),
                "freshness": round(FRESHNESS_MAP.get(cls, 0.0), 3),
                "boundingBox": {
                    "x": round(nx, 4), "y": round(ny, 4),
                    "width": round(nw, 4), "height": round(nh, 4),
                },
            })
        outputs.append(dets)

    return outputs[0] if single_input else outputs

# --- 🔑 인증 의존성 ---
async def get_current_user(Authorization: str = Header(None), db: Session = Depends(get_db)):
    """
    요청 헤더의 Authorization 필드에서 Bearer 토큰을 파싱하고 유저를 반환합니다.
    """
    if Authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 필요합니다.",
        )
        
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="자격 증명을 확인할 수 없습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # "Bearer " 접두사가 있는지 확인하고 제거합니다.
        token_prefix = "Bearer "
        if not Authorization.startswith(token_prefix):
            raise credentials_exception
        
        token = Authorization[len(token_prefix):]
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
        
    return user

# --- 📝 회원가입 ---
@auth_router.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    # 이메일 중복 체크
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다.")
    if db.query(User).filter(User.nickname == user.nickname).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 닉네임입니다.")
    if user.password != user.password_confirm:
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    hashed_pw = hash_password(user.password)
    new_user = User(nickname=user.nickname, email=user.email, password_hash=hashed_pw, is_verified=True)
    db.add(new_user)
    db.commit()

    # 이메일 인증 토큰 발송
    token = jwt.encode({"sub": user.email}, SECRET_KEY, algorithm=ALGORITHM)
    BACKEND_ORIGIN = os.getenv("BACKEND_ORIGIN", "http://localhost:8000")
    verification_link = f"{BACKEND_ORIGIN}/auth/verify/{token}"
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = os.getenv("SMTP_PORT", 587)
    SMTP_USER = os.getenv("SMTP_USER", "forgpt0405@gmail.com")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "oxtf iqer cmuj klzr")  # Gmail 앱 비밀번호 사용 권장

    def send_email(to_email: str, verify_link: str):
        subject = "바나나-리텍스 회원가입 이메일 인증"
        body = f"""
        안녕하세요! 🍌

        아래 링크를 클릭해 이메일 인증을 완료해주세요:
        {verify_link}

        감사합니다!
        """

        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, to_email, msg.as_string())
            print("✅ 인증 메일 발송 성공:", to_email)
        except Exception as e:
            print("❌ 인증 메일 발송 실패:", e)
    send_email(user.email, verification_link) 

    return {"message": "이메일 인증 메일이 발송되었습니다."}

@auth_router.get("/verify/{token}")
def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        user.is_verified = 1
        db.commit()
        return {"message": "이메일 인증이 완료되었습니다. 이제 로그인할 수 있습니다."}
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 또는 만료된 토큰입니다.")

# --- 🔐 로그인 ---
@auth_router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="존재하지 않는 이메일입니다.")
    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="이메일 인증 후 로그인 가능합니다.")

    access_token = jwt.encode({
        "sub": user.email,
        "nickname": user.nickname,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": access_token, "token_type": "bearer"}

# 통계 갱신 전용 함수
def update_daily_analysis_stat(db: Session, target_date: date):
    label_score = LABEL_SCORE

    start_dt = datetime.combine(target_date, dtime.min).astimezone(KST)
    end_dt = datetime.combine(target_date, dtime.max).astimezone(KST)

    records = db.query(Analysis).filter(
        Analysis.created_at >= start_dt,
        Analysis.created_at <= end_dt,
        Analysis.ripeness != "비디오분석",
        Analysis.confidence.isnot(None),
        Analysis.confidence > 0
    ).all()

    if not records:
        stat = db.query(DailyAnalysisStat).filter(DailyAnalysisStat.date == target_date).first()
        if not stat:
            stat = DailyAnalysisStat(date=target_date)
            db.add(stat)

        stat.total_count = 0
        stat.accuracy = 0.0
        stat.freshness = 0.0
        stat.variety_count = 0

        db.commit()
        return

    total = len(records)
    avg_conf = sum(r.confidence for r in records) / total

    # ✅ 정확도 보정 로직 (100 넘으면 잘못 저장된 값이므로 1로 나눠서 보정)
    if avg_conf > 1.0:
        print(f"[경고] 평균 confidence 값 {avg_conf}가 1.0 초과 → 100 나눠서 보정함")
        avg_conf = avg_conf / 100

    avg_conf_percent = avg_conf * 100

    avg_fresh = sum(label_score.get(r.ripeness, 0) for r in records) / total
    variety = len(set(r.ripeness for r in records))

    stat = db.query(DailyAnalysisStat).filter(DailyAnalysisStat.date == target_date).first()
    if not stat:
        stat = DailyAnalysisStat(date=target_date)
        db.add(stat)

    stat.total_count = total
    stat.accuracy = round(avg_conf_percent, 2)  # 퍼센트로 저장
    stat.freshness = round(avg_fresh, 2)
    stat.variety_count = variety

    db.commit() 

# --- 📹 비동기 작업 및 동영상 생성 ---
def decode_bgr(img_bytes: bytes) -> np.ndarray:
    """
    JPEG EXIF Orientation을 반영해서 올바른 방향의 BGR ndarray로 반환.
    브라우저가 보여주는 방향과 서버가 계산하는 방향을 일치시킵니다.
    """
    try:
        pil = Image.open(BytesIO(img_bytes))
        pil = ImageOps.exif_transpose(pil)     # ★ 방향 교정
        pil = pil.convert("RGB")               # 보장
        arr = np.array(pil)[:, :, ::-1].copy() # RGB->BGR
        return arr
    except Exception:
        # 폴백: cv2.imdecode (EXIF 무시하지만, 최후의 안전망)
        arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("이미지 디코딩 실패")
        return img

def decode_and_cover(img_bytes: bytes, dst_w: int, dst_h: int) -> np.ndarray:
    """
    EXIF 교정된 BGR로 디코드 → 여백 없이 cover 크롭.
    """
    img = decode_bgr(img_bytes)                # ★ 방향 먼저 맞추고
    return resize_cover(img, dst_w, dst_h)     # 그다음 cover로 자르기

# --- 여백 없이 정사이즈로 맞추기(cover)
def resize_cover(img_bgr: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    if w == 0 or h == 0:
        raise ValueError("invalid image size")
    scale = max(out_w / w, out_h / h)  # 빈 공간 없이 채우도록
    nw, nh = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x1 = max(0, (nw - out_w) // 2)
    y1 = max(0, (nh - out_h) // 2)
    return resized[y1:y1 + out_h, x1:x1 + out_w].copy()

# ▼ Environment knobs
SCROLL_FPS = int(os.getenv("SCROLL_FPS", "13"))
SECONDS_PER_TILE = float(os.getenv("SECONDS_PER_TILE", "1.6"))

# ────────────────────────────────────────────────────────────────────────────────
# Helpers for the scroll video pipeline
# ────────────────────────────────────────────────────────────────────────────────
def _shift_norm_boxes(dets: list, dx_norm: float) -> list:
    """정규화 박스들을 x방향으로 dx_norm만큼 평행이동(+클램프)."""
    out = []
    for d in dets or []:
        bb = d.get("boundingBox") or {}
        x = float(bb.get("x", 0.0)) + dx_norm
        y = float(bb.get("y", 0.0))
        w = float(bb.get("width", 0.0))
        h = float(bb.get("height", 0.0))
        # 경계 클램프 및 우측 넘침 보정
        x = max(0.0, min(1.0, x))
        w = max(0.0, min(1.0 - x, w))
        out.append({
            "boundingBox": {"x": x, "y": max(0.0, min(1.0, y)),
                            "width": w, "height": max(0.0, min(1.0 - y, h))},
            "ripeness": d.get("ripeness", ""),
            "confidence": float(d.get("confidence", 0.0)),
        })
    return out

# 최소한의 오버레이(박스/라벨) 함수 — 한글 폰트, 경계 클램프 포함
def draw_overlay(frame_bgr, detections, w=None, h=None):
    if not detections:
        return
    import cv2, numpy as np
    from PIL import Image, ImageDraw, ImageFont

    # 프레임 크기
    if w is None or h is None:
        h, w = frame_bgr.shape[:2]

    # 선 두께
    thickness = max(2, min(6, (w + h) // 400))

    # 1) OpenCV 박스 (정규화 → 픽셀 + 클램프)
    for d in detections:
        bb = d.get("boundingBox") or {}
        nx = max(0.0, min(1.0, float(bb.get("x", 0.0))))
        ny = max(0.0, min(1.0, float(bb.get("y", 0.0))))
        nw = max(0.0, min(1.0 - nx, float(bb.get("width", 0.0))))
        nh = max(0.0, min(1.0 - ny, float(bb.get("height", 0.0))))

        x1 = int(round(nx * w))
        y1 = int(round(ny * h))
        x2 = int(round((nx + nw) * w))
        y2 = int(round((ny + nh) * h))

        # 프레임 경계 내로 강제
        x1 = max(0, min(w - 2, x1))
        y1 = max(0, min(h - 2, y1))
        x2 = max(x1 + 1, min(w - 1, x2))
        y2 = max(y1 + 1, min(h - 1, y2))

        cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 255), thickness)

    # 2) PIL 라벨 (한글 폰트)
    if not globals().get("SHOW_LABELS", True):
        return

    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # _get_font가 있다면 사용, 없으면 안전 폴백
    try:
        font = _get_font(22)  # 프로젝트에 이미 있는 함수
    except Exception:
        try:
            font = ImageFont.truetype("NanumGothic.ttf", size=22)
        except Exception:
            font = ImageFont.load_default()  # 한글 미지원일 수 있음

    for d in detections:
        bb = d.get("boundingBox") or {}
        nx = max(0.0, min(1.0, float(bb.get("x", 0.0))))
        ny = max(0.0, min(1.0, float(bb.get("y", 0.0))))
        x1 = int(round(nx * w))
        y1 = int(round(ny * h))

        label = f"{d.get('ripeness','')} {float(d.get('confidence',0.0))*100:.1f}%".strip()
        if not label:
            continue

        l, t, r, btm = draw.textbbox((0, 0), label, font=font)
        tw, th = (r - l), (btm - t)
        pad = 6
        box_w, box_h = tw + pad * 2, th + pad * 2

        # X는 프레임 안
        x = max(0, min(w - box_w, x1))

        # Y는 위에 자리 있으면 위, 없으면 박스 안, 그것도 안 되면 하단
        if y1 - box_h - 2 >= 0:
            y = y1 - box_h - 2
        elif y1 + 2 + box_h <= h:
            y = y1 + 2
        else:
            y = max(0, h - box_h)

        bg = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 210))
        img.paste(bg, (x, y), bg)
        draw.text((x + pad, y + pad), label, font=font, fill=(255, 255, 255, 255))

    frame_bgr[:] = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

def decode_and_cover(img_bytes: bytes, dst_w: int, dst_h: int) -> np.ndarray:
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("이미지 디코딩 실패")
    return resize_cover(img, dst_w, dst_h)

def _iter_tiles_cover_from_manifest(manifest: List[Dict[str, str]], out_w: int, out_h: int):
    """디스크에서 바로 1장씩 읽어서 cover-resize 후 yield. 메모리 O(1)."""
    for m in manifest:
        with open(m["path"], "rb") as fp:
            data = fp.read()
        yield decode_and_cover(data, out_w, out_h)

def _compose_frame_from_tiles(tile_left: np.ndarray, tile_right: np.ndarray, offset: int, view_w: int) -> np.ndarray:
    left_part  = tile_left[:, offset:view_w]
    right_part = tile_right[:, :offset] if offset > 0 else None
    return left_part.copy() if right_part is None or right_part.shape[1] == 0 else np.hstack([left_part, right_part])

def _write_scroll_video_stream_raw_streaming(manifest: List[Dict[str, str]], out_path: str, fps: int) -> None:
    """타일 리스트 없이 인접 타일 2장만으로 스크롤 비디오 생성."""
    view_w, view_h = TARGET_W, TARGET_H
    it = _iter_tiles_cover_from_manifest(manifest, view_w, view_h)
    try:
        left = next(it)
    except StopIteration:
        raise ValueError("no tiles")

    # 인코더
    using_ffmpeg, proc, vw = False, None, None
    if shutil.which("ffmpeg") and USE_FFMPEG: 
        cmd = ["ffmpeg","-y","-loglevel","error","-f","rawvideo","-pix_fmt","bgr24",
               "-s", f"{view_w}x{view_h}","-r", str(fps), "-i","-",
               "-c:v","libx264","-preset","ultrafast","-crf","30",
               "-threads","1","-max_muxing_queue_size","64","-bufsize","2M",
               "-pix_fmt","yuv420p","-movflags","+faststart", out_path]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.stdin is None: raise RuntimeError("failed to open ffmpeg stdin")
        using_ffmpeg = True
    else:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        vw = cv2.VideoWriter(out_path, fourcc, fps, (view_w, view_h))
        if not vw.isOpened(): raise RuntimeError("VideoWriter open failed")

    frames_per_tile = max(1, int(round(SECONDS_PER_TILE * fps)))
    step = max(1, view_w // frames_per_tile)

    try:
        wrote_any = False
        for right in it:
            for off in range(0, view_w, step):
                frame = _compose_frame_from_tiles(left, right, off, view_w)
                if using_ffmpeg: proc.stdin.write(frame.tobytes())
                else:            vw.write(frame)
                wrote_any = True
            # 다음 경계로 이동
            left = right
            # 스트리밍이므로 참조 해제
            del right, frame
        # 마지막 타일 hold
        for _ in range(frames_per_tile):
            if using_ffmpeg: proc.stdin.write(left.tobytes())
            else:            vw.write(left)
        wrote_any = True
    finally:
        if using_ffmpeg:
            try: proc.stdin.close()
            except: pass
            proc.wait(timeout=30)
        else:
            vw.release()
        del left
        import gc; gc.collect()

FRAME_STRIDE = int(os.getenv("FRAME_STRIDE", "1")) 

FRAME_STRIDE = int(os.getenv("FRAME_STRIDE", "2"))               # ← 기본 2로
VIDEO_INFER_SIZE = int(os.getenv("VIDEO_INFER_SIZE", "640"))     # ← 512~640 권장

def detect_video_and_write(input_path: str, output_path: str) -> None:
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError("cannot open input video")

    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps    = cap.get(cv2.CAP_PROP_FPS) or SCROLL_FPS

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not out.isOpened():
        cap.release()
        raise RuntimeError("cannot open output video")

    # 스크롤 비디오에서 프레임당 수평 이동량(px)을 추정
    frames_per_tile = max(1, int(round(SECONDS_PER_TILE * fps)))
    pan_step_px = max(1, width // frames_per_tile)   # compose 때 사용한 step과 동일 로직
    pan_step_norm = pan_step_px / float(width)       # 정규화 이동량

    names = getattr(model, "names", {}) or {}

    try:
        import torch, gc
        torch.set_num_threads(max(1, int(os.getenv("TORCH_NUM_THREADS", "1"))))

        i = 0
        last_dets = None
        last_det_i = -1

        with torch.inference_mode():
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                run_detect = (i % FRAME_STRIDE == 0)
                dets_for_draw = None

                if run_detect:
                    # ↓↓↓ YOLO 추론 크기 축소 + 로그 끔
                    results = model(frame, imgsz=VIDEO_INFER_SIZE, conf=FINAL_CONF, verbose=False)
                    dets = []
                    if results and len(results) > 0:
                        r = results[0]
                        boxes = getattr(r, "boxes", None)
                        if boxes is not None and boxes.xyxy is not None:
                            xyxy = boxes.xyxy.cpu().numpy()
                            conf = boxes.conf.cpu().numpy()
                            cls  = boxes.cls.cpu().numpy().astype(int)
                            h, w = frame.shape[:2]
                            inv_w, inv_h = 1.0 / w, 1.0 / h
                            for (x1, y1, x2, y2), c, k in zip(xyxy, conf, cls):
                                dets.append({
                                    "boundingBox": {
                                        "x":      float(x1 * inv_w),
                                        "y":      float(y1 * inv_h),
                                        "width":  float((x2 - x1) * inv_w),
                                        "height": float((y2 - y1) * inv_h),
                                    },
                                    "ripeness": str(names.get(int(k), str(k))),
                                    "confidence": float(c),
                                })

                    last_dets = dets
                    last_det_i = i
                    dets_for_draw = dets

                else:
                    # 탐지 건너뜀 → 이전 결과를 팬 이동량만큼 왼쪽(-)으로 평행이동
                    if last_dets is not None and last_det_i >= 0:
                        since = i - last_det_i
                        dx_norm = - since * pan_step_norm
                        dets_for_draw = _shift_norm_boxes(last_dets, dx_norm)

                # 그리기(건너뛴 프레임도 박스는 보이게)
                if dets_for_draw:
                    draw_overlay(frame, dets_for_draw, width, height)

                out.write(frame)
                if (i % 32) == 0:
                    gc.collect()
                i += 1
    finally:
        cap.release()
        out.release()

def create_scroll_then_detect_video(current_user, task_id: str, manifest: List[Dict[str, str]]) -> None:
    view_w, view_h = TARGET_W, TARGET_H
    raw_video_path   = RESULTS_DIR / f"{task_id}_raw.mp4"
    final_video_path = RESULTS_DIR / f"{task_id}_final.mp4"

    _write_scroll_video_stream_raw_streaming(manifest, str(raw_video_path), fps=SCROLL_FPS)
    if not raw_video_path.exists() or raw_video_path.stat().st_size == 0: raise IOError("raw scroll video empty")

    detect_video_and_write(str(raw_video_path), str(final_video_path))
    if not final_video_path.exists() or final_video_path.stat().st_size == 0: raise IOError("final video empty")

    try: raw_video_path.unlink(missing_ok=True)
    except Exception: pass

    db = SessionLocal()
    try:
        username = getattr(current_user, "nickname", None) or "unknown"
        db.add(Analysis(
            username=username, ripeness="영상기반",
            confidence=0.0, freshness=0.0,
            video_path=f"/results/{final_video_path.name}",
            video_blob=None, created_at=datetime.now(timezone("Asia/Seoul")),
        ))
        db.commit(); update_daily_analysis_stat(db, datetime.now(timezone("Asia/Seoul")).date())
    finally:
        db.close()

    db = SessionLocal()
    try: set_task_db(db, task_id, status="SUCCESS", result=f"/results/{final_video_path.name}")
    finally: db.close()

# --- 동영상 스트리밍 함수 ---
@app.get("/results/{filename}")
def get_result_file(filename: str):
    root = RESULTS_DIR.resolve()
    candidate = (root / filename).resolve()

    # 🔒 /results 디렉터리 밖 접근 방지
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found")

    if not candidate.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        candidate,
        media_type="video/mp4",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Accept-Ranges": "bytes",  "X-Content-Type-Options": "nosniff"}
    )

# --- 분석 라우터 (모든 API에 인증 필요) ---
@analysis_router.post("/analyze")
async def analyze_single_image(payload: ImagePayload, current_user: User = Depends(get_current_user)):
    if not MODEL_READY or model is None:
        raise HTTPException(status_code=503, detail="모델이 준비 중입니다. 잠시 후 다시 시도해주세요.")
    try:
        img_bytes = base64.b64decode(payload.image)

        # ✅ 원본으로 디코드 (letterbox 사용 X)
        img_bgr = decode_bgr(img_bytes)

        loop = asyncio.get_running_loop()

        # run_yolo_np_bgr 이 단일 이미지 버전이면 그대로,
        # 배치(List[np.ndarray]) 버전이면 [img_bgr][0] 으로 꺼내세요.
        detections = await loop.run_in_executor(EXECUTOR, run_yolo_np_bgr, img_bgr, (MODEL_W, MODEL_H,), FINAL_CONF, 100)

        avg_conf = round((sum(d["confidence"] for d in detections) / len(detections)) if detections else 0.0, 4)
        avg_fresh = round((sum(d["freshness"] for d in detections) / len(detections)) if detections else 0.0, 4)

        h, w = img_bgr.shape[:2]
        new_w = 512
        new_h = max(1, int(h * (new_w / max(1, w))))
        thumb_bgr = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        thumb = cv2.imencode(".jpg", thumb_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])[1].tobytes()

        db = SessionLocal()
        try:
            db.add(Analysis(
                username=current_user.nickname,
                ripeness=detections[0]["ripeness"] if detections else "분석불가",
                confidence=avg_conf,
                freshness=avg_fresh,
                image_blob=thumb,                         # <<< 여기!
                created_at=datetime.now(KST)
            ))
            increment_daily_box_counts(db, detections)
            db.commit()
            update_daily_analysis_stat(db, datetime.now(KST).date())
        finally:
            db.close()

        return {"detections": detections, "avg_confidence": avg_conf}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 분석 중 오류: {e}")

# 앞의 N장만 즉시 추론
FAST_PREVIEW = 2

@analysis_router.post("/analyze_video")
async def start_video_analysis(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    if not files:
        raise HTTPException(status_code=400, detail="동영상 분석을 위해서는 1장 이상의 이미지가 필요합니다.")
    if MAX_FILES and len(files) > MAX_FILES:
        raise HTTPException(status_code=413, detail=f"이미지는 최대 {MAX_FILES}장까지 업로드 가능합니다.")

    task_id = str(uuid.uuid4())
    with SessionLocal() as db:
        set_task_db(db, task_id, status="PENDING", result=None, image_results=[])

    loop = asyncio.get_running_loop()

    # 0) 업로드만 디스크에 저장
    task_root = TASKS_DIR / task_id
    orig_dir  = task_root / "orig"
    orig_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []        # [{'filename':..., 'path':...}]
    image_results: list[dict] = []   # 프리뷰/폴링용 결과

    for f in files[:MAX_FILES]:
        dst = orig_dir / f.filename
        size = 0
        with open(dst, "wb") as out:
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if MAX_BYTES and size > MAX_BYTES:
                    out.close()
                    dst.unlink(missing_ok=True)
                    image_results.append({
                        "filename": f.filename, "detections": [], "avg_confidence": 0,
                        "error": f"파일 용량(최대 {MAX_BYTES//1024//1024}MB) 초과"
                    })
                    break
                out.write(chunk)
        await f.close()
        if MAX_BYTES and size > MAX_BYTES:
            continue
        manifest.append({"filename": f.filename, "path": str(dst)})

    if not manifest and not image_results:
        with SessionLocal() as db:
            set_task_db(db, task_id, status="FAILURE", result="유효한 이미지가 없습니다.", image_results=image_results)
        return {"task_id": task_id, "results": image_results}

    # 1) FAST_PREVIEW 장만 즉시 추론 (여기엔 '배치/비디오재료' 코드가 있으면 안 됨)
    for i, itm in enumerate(manifest):
        if i >= FAST_PREVIEW:
            image_results.append({"filename": itm["filename"], "detections": [], "avg_confidence": None, "processed": False,})
            continue
        try:
            with open(itm["path"], "rb") as fp:
                data = fp.read()
            bgr  = await loop.run_in_executor(EXECUTOR, decode_and_cover, data, TARGET_W, TARGET_H)
            dets = await loop.run_in_executor(EXECUTOR, run_yolo_np_bgr, bgr, (MODEL_W, MODEL_H,), FINAL_CONF, 100)
            avg_conf = round(sum(d["confidence"] for d in dets) / len(dets), 4) if dets else 0.0
            image_results.append({"filename": itm["filename"], "detections": dets, "avg_confidence": avg_conf, "processed": True})
        except Exception as e:
            image_results.append({"filename": itm["filename"], "detections": [], "avg_confidence": 0, "processed": True, "error": str(e)})

    # 2) 초기 상태 저장 후 즉시 응답 준비
    with SessionLocal() as db:
        set_task_db(db, task_id, status="PROCESSING", image_results=image_results)

    # 3) 나머지는 백그라운드에서 처리 (배치 추론 + 점진 저장 + 최종 비디오 생성)
    def bg_finish_and_render():
        try:
            name_to_result = {r["filename"]: r for r in image_results}

            pending = [m for m in manifest if not name_to_result.get(m["filename"], {}).get("detections")]

            # --- 배치 추론 (디코드 즉시, 보관 최소화) ---
            for i in range(0, len(pending), max(1, BATCH_SIZE)):
                batch = pending[i:i + BATCH_SIZE]
                batch_imgs, batch_names = [], []
                for itm in batch:
                    with open(itm["path"], "rb") as fp:
                        data = fp.read()
                    img = decode_and_cover(data, TARGET_W, TARGET_H)
                    batch_imgs.append(img)
                    batch_names.append(itm["filename"])

                det_lists = run_yolo_np_bgr(batch_imgs, imgsz=(MODEL_W, MODEL_H,), conf=FINAL_CONF, max_det=100)

                for fname, dets in zip(batch_names, det_lists):
                    avg_conf = round(sum(d["confidence"] for d in dets) / len(dets), 4) if dets else 0.0
                    name_to_result[fname] = {"filename": fname, "detections": dets, "avg_confidence": avg_conf, "processed": True,}

                with SessionLocal() as db:
                    sorted_results = []
                    for m in manifest:
                        r = name_to_result.get(m["filename"], {})
                        sorted_results.append({
                            "filename": m["filename"],
                            "detections": r.get("detections", []),
                            "avg_confidence": r.get("avg_confidence", 0.0),
                            "processed": bool(r.get("processed", False)),
                            "error": r.get("error")  # 있으면 포함
                        })
                    set_task_db(db, task_id, status="PROCESSING", image_results=sorted_results)
                del batch_imgs, det_lists
                import gc; gc.collect()

            # --- 최종 비디오---
            create_scroll_then_detect_video(current_user, task_id, manifest)

        except MemoryError:
            with SessionLocal() as db:
                set_task_db(db, task_id, status="FAILURE", result="Out of memory (512MB 한도 초과)")
        except Exception as e:
            with SessionLocal() as db:
                set_task_db(db, task_id, status="FAILURE", result=str(e))


    threading.Thread(target=bg_finish_and_render, daemon=True).start()

    # 4) 프론트는 task_id 폴링
    return {"task_id": task_id, "results": image_results}

# 일일 박스 카운트 증가
def increment_daily_box_counts(db: Session, detections: list):
    """
    detections: [{ripeness: "...", ...}, ...]  (한 이미지의 결과)
    오늘 날짜의 클래스별 박스 카운트를 증가합니다.
    """
    today = datetime.now(KST).date()
    row = db.query(DailyBoxCount).get(today)
    if not row:
        row = DailyBoxCount(date=today, counts_json="{}")
        db.add(row)

    current = Counter(json.loads(row.counts_json or "{}"))
    inc = Counter(d.get("ripeness", "분석불가") for d in (detections or []))
    current.update(inc)

    row.counts_json = json.dumps(current, ensure_ascii=False)
    db.commit()

def increment_daily_box_counts_bulk(db: Session, frames_with_dets: List[Tuple[np.ndarray, list]]):
    today = datetime.now(KST).date()
    row = db.query(DailyBoxCount).get(today)
    if not row:
        row = DailyBoxCount(date=today, counts_json="{}")
        db.add(row)

    current = Counter(json.loads(row.counts_json or "{}"))

    for _, dets in frames_with_dets:
        current.update(Counter(d.get("ripeness", "분석불가") for d in (dets or [])))

    row.counts_json = json.dumps(current, ensure_ascii=False)
    db.commit()

# --- 작업 상태 확인 라우터 (인증 필요 없음) ---
@task_router.get("/{task_id}/status")
async def get_task_status(task_id: str, request: Request):
    db = SessionLocal()
    try:
        task = get_task_db(db, task_id)
    finally:
        db.close()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result = task.get("result")
    absolute_result = None

    if isinstance(result, str) and result:
        if result.startswith("http://") or result.startswith("https://"):
            absolute_result = result
        elif result.startswith("/"):
            # 1) x-forwarded-* 우선
            proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
            host  = (request.headers.get("x-forwarded-host")  or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
            candidate = f"{proto}://{host}{result}"

            # 2) base_url 폴백 (프록시 헤더가 틀릴 때)
            base = str(request.base_url).rstrip("/")
            if not proto or not host:
                absolute_result = f"{base}{result}"
            else:
                absolute_result = candidate or f"{base}{result}"

    return {
        "status": task.get("status"),
        "result": result,
        "absolute_result": absolute_result,
        "image_results": task.get("image_results", []),
    }

# --- 통계 라우터 ---
@stats_router.get("/", response_model=dict)
def get_stats(db: Session = Depends(get_db)):
    today = datetime.now(KST).date()

    # ✅ 통계 테이블에서 오늘자 데이터 가져옴
    today_stat = db.query(DailyAnalysisStat).filter(DailyAnalysisStat.date == today).first()

    box_row = db.query(DailyBoxCount).get(today)
    ripeness_counts = json.loads(box_row.counts_json or "{}") if box_row else {}

    if not today_stat:
        # 통계가 없으면 0으로 리턴 (혹은 update_daily_analysis_stat() 호출도 가능)
        return {
            "todayAnalyses": 0,
            "avgRipeness": 0.0,
            "totalUploads": db.query(Analysis).count(),
            "ripeness_counts": {}
        }

    return {
        "todayAnalyses": today_stat.total_count,
        "avgRipeness": round(today_stat.freshness, 2),
        "totalUploads": db.query(Analysis).count(),
        "ripeness_counts": ripeness_counts
    }

@stats_router.get("/daily")
def get_daily_stats(db: Session = Depends(get_db)):
    today = datetime.now(KST).date()
    update_daily_analysis_stat(db, today)  # 오늘만 업데이트

    # ✅ 기존 통계들 불러오기 (덮어쓰기 안함!)
    rows = db.query(DailyAnalysisStat).order_by(DailyAnalysisStat.date).all()
    return [
        {
            "date": r.date.strftime("%Y-%m-%d"),
            "total": r.total_count,
            "avg_confidence": r.accuracy,
            "avg_freshness": r.freshness,
            "variety": r.variety_count
        }
        for r in rows
    ]

# ✅ 특정 날짜 기준 분석 통계 계산 함수
def get_analysis_stats_by_date(db: Session, target_date: date):
    start_dt = datetime.combine(target_date, dtime.min).astimezone(KST)
    end_dt = datetime.combine(target_date, dtime.max).astimezone(KST)

    records = db.query(Analysis).filter(
        Analysis.created_at >= start_dt,
        Analysis.created_at <= end_dt,
        Analysis.ripeness != "비디오분석",
        Analysis.confidence.isnot(None),
        Analysis.confidence > 0,
        Analysis.freshness.isnot(None),
        Analysis.freshness > 0
    ).all()

    if not records:
        return 0, 0.0, 0.0, {}

    count = len(records)

    # confidence는 항상 존재한다고 가정
    avg_conf = sum(r.confidence for r in records) / count
    avg_conf = avg_conf * 100

    # freshness는 None을 제거하고 계산
    fresh_values = [r.freshness for r in records if r.freshness is not None]
    avg_fresh = sum(fresh_values) / len(fresh_values) if fresh_values else 0.0

    ripeness_counts = {}
    for r in records:
        ripeness_counts[r.ripeness] = ripeness_counts.get(r.ripeness, 0) + 1

    return count, avg_conf, avg_fresh, ripeness_counts

@stats_router.get("/summary")
def get_summary_stats():
    db = SessionLocal()
    try:
        today = datetime.now(KST).date()
        yesterday = today - timedelta(days=1)

        today_stat = db.query(DailyAnalysisStat).filter(DailyAnalysisStat.date == today).first()
        yest_stat = (
            db.query(DailyAnalysisStat)
            .filter(DailyAnalysisStat.date < today)
            .order_by(DailyAnalysisStat.date.desc())
            .first()
        )

        total_count = db.query(func.count(Analysis.id)).scalar()

        today_start = datetime.combine(today, dtime.min).astimezone(KST)
        total_before_today = db.query(func.count(Analysis.id)).filter(
            Analysis.created_at < today_start
        ).scalar()

        box_today = db.query(DailyBoxCount).get(today)
        today_box = json.loads(box_today.counts_json or "{}") if box_today else {}
        # 파이차트 데이터
        ripeness_counts = {k: int(v) for k, v in today_box.items() if k != "비디오분석"}
        # 다양성(>0 인 클래스 수)
        today_variety = sum(1 for v in ripeness_counts.values() if int(v) > 0)

        # ✅ 어제 다양성도 DailyBoxCount 기준으로
        box_yest = db.query(DailyBoxCount).get(yesterday)
        yest_box = json.loads(box_yest.counts_json or "{}") if box_yest else {}
        yesterday_variety = sum(
            1 for k, v in yest_box.items()
            if k != "비디오분석" and int(v) > 0
        )

        # 정확도 값 안전 처리
        acc_today = round(today_stat.accuracy or 0, 2) if today_stat else 0.0
        acc_yest = round(yest_stat.accuracy or 0, 2) if yest_stat else 0.0
        fresh_today = today_stat.freshness if today_stat else 0.0
        fresh_yest = yest_stat.freshness if yest_stat else 0.0
        
        return {
            "today": today_stat.total_count if today_stat else 0,
            "yesterday": yest_stat.total_count if yest_stat else 0,
            "total": total_count,
            "total_before_today": total_before_today,

            # ✅ 파이차트: 박스 기준
            "ripeness_counts": ripeness_counts,

            # ✅ 다양성: 박스 기준(오늘/어제)
            "today_variety": today_variety,
            "yesterday_variety": yesterday_variety,

            "avg_confidence_today": acc_today,
            "avg_confidence_yesterday": acc_yest,
            "avg_freshness_today": fresh_today,
            "avg_freshness_yesterday": fresh_yest,
        }

    except Exception as e:
        print(f"[❌ 에러 발생] {e}")
        raise
    finally:
        db.close()

# 서버 제한값을 환경변수화 + 프론트에 자동 전파

def _int(name, default): return int(os.getenv(name, str(default)))

@settings_router.get("")
@settings_router.get("/")
def get_settings():
    return {
        "MODEL_W": _int("MODEL_W", 640),
        "MODEL_H": _int("MODEL_H", 480),
        "MAX_FILES": _int("MAX_FILES", 15),
        "MAX_BYTES": _int("MAX_BYTES", 8*1024*1024),
        "VIDEO_FPS": VIDEO_FPS,          # ← 변수 사용
        "INFER_EVERY_N_FRAMES": _int("INFER_EVERY_N_FRAMES", 10),
        "FRAME_STRIDE": FRAME_STRIDE,
    }


# --- 최종 라우터 등록 ---
app.include_router(auth_router,      prefix="/auth")
app.include_router(analysis_router,  prefix="/analysis") 
app.include_router(task_router,      prefix="/tasks")
app.include_router(stats_router,     prefix="/stats")
app.include_router(settings_router,  prefix="/settings")

# --- ✅ 루트 확인용 ---
@app.get("/")
def root():
    return {"message": "🍌 바나나 YOLO 분석 서버 작동 중"}