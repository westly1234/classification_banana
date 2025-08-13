# --- 📁 backend/main.py ---

import os, asyncio, concurrent.futures, base64, io, uuid, threading, time, smtplib, pytz, cv2, torch, numpy as np
from datetime import datetime, timedelta, date, time as dtime
from pytz import timezone
from pathlib import Path
from markupsafe import Markup
from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True # 손상/부분 이미지도 최대한 로드
from dotenv import load_dotenv
load_dotenv()

from collections import Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# FastAPI 및 관련 라이브러리
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Request, status, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from typing import List

# 인증 관련 라이브러리
from jose import jwt, JWTError
from passlib.context import CryptContext

# SQLAlchemy 관련 import 문 추가
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, func, LargeBinary
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base

# SQLAdmin 관련 import 문 추가
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend

# Pydantic 및 YOLO
from pydantic import BaseModel
from ultralytics import YOLO

# 로컬 DB 및 모델 초기화
from db import engine, SessionLocal, init_db
from models import User, Analysis, DailyAnalysisStat

init_db()
# --- 한국 시간 설정 ---
KST = pytz.timezone("Asia/Seoul")
def get_kst_now():
    return datetime.now(KST)

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
# Render 환경에서는 DATABASE_URL 환경 변수를 사용하고, 로컬에서는 SQLite를 사용합니다.
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres"):
    # Render의 PostgreSQL URL 형식에 맞게 드라이버 이름을 변경합니다.
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5, max_overflow=5,
        pool_recycle=180,     # ✅ 3분마다 커넥션 재활용
        pool_timeout=30,
        connect_args={"sslmode":"require"}  # URL에 ?sslmode=require가 있으면 생략 가능
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    # 로컬 개발 환경용 SQLite 설정
    print("⚠️  DATABASE_URL 환경 변수를 찾을 수 없습니다. 로컬 SQLite DB를 사용합니다.")
    SQLALCHEMY_DATABASE_URL = "sqlite:///./users.db"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) 

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

# (원하면 문서 숨김: docs_url=None, redoc_url=None)
app = FastAPI(title="바나나 YOLO 분석")

admin = Admin(app, engine, authentication_backend=SimpleAuth(secret_key=SECRET_KEY))
admin.add_view(UserAdmin)
admin.add_view(AnalysisAdmin)

# --- CORS 설정 ---
FRONT_REGEX = r"^https://classification-banana(-[0-9]+)?\.onrender\.com$"
LOCAL = "http://localhost:5173"

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=FRONT_REGEX,   # ✅ 정규식
    allow_origins=[LOCAL],            # 로컬은 정확히 지정
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ 세션 쿠키 보안 옵션 (SQLAdmin용)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=True,
    same_site="lax",
    max_age=60 * 60 * 8,  # 8시간
)

# ✅ 결과 폴더
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# --- 라우터 생성 ---
auth_router = APIRouter(tags=["Authentication"])
analysis_router = APIRouter(tags=["Analysis"])
task_router = APIRouter(tags=["Tasks"])
stats_router = APIRouter(tags=["Statistics"])
settings_router = APIRouter(tags=["Settings"])

# 작업 상태 임시 저장소
tasks = {}

# --- DB 세션 종속성 ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- YOLO 로드 ---
BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "best.pt"

try:
    model = YOLO(MODEL_PATH)
    print("✅ YOLO 모델 로딩 성공!")
except Exception as e:
    print(f"❌ YOLO 모델 로딩 실패: {e}")
    # 모델 로딩에 실패하면 서버가 시작되지 않도록 처리할 수도 있습니다.
    model = None

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

# YOLO/CPU 튜닝: 무료 1코어 환경 고려
cv2.setNumThreads(1)
torch.set_num_threads(max(1, (os.cpu_count() or 1) // 2))

# 해상도 일관화(모델/전처리/비디오 공통)
MODEL_W = int(os.getenv("MODEL_W", "640"))
MODEL_H = int(os.getenv("MODEL_H", "480"))
TARGET_W = int(os.getenv("TARGET_W", str(MODEL_W)))  # 비디오/표시 해상도
TARGET_H = int(os.getenv("TARGET_H", str(MODEL_H)))

# 업로드 제한(환경변수로 크게 조정 가능)
MAX_FILES = int(os.getenv("MAX_FILES", "20"))                 # 프론트는 제한 제거(아래 4번), 서버는 안전빵
MAX_BYTES = int(os.getenv("MAX_BYTES", str(10*1024*1024)))    # 10MB/파일

# 추론 전용 스레드풀(ADD)
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2)

#  비디오 생성(멀티 이미지) 최적화 + 해상도 키우기
INFER_EVERY_N_FRAMES = int(os.getenv("INFER_EVERY_N_FRAMES", "10"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "8"))
SECONDS_PER_IMAGE = float(os.getenv("SECONDS_PER_IMAGE", "1.0"))

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

def run_yolo_np_bgr(img_bgr: np.ndarray):
    if not model:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="모델을 사용할 수 없습니다.")

    # img_bgr는 이미 (MODEL_H, MODEL_W) 레터박스 상태라고 가정
    results = model(img_bgr, imgsz=(MODEL_W, MODEL_H), conf=0.1, verbose=False)[0]

    analysis_results = []
    VALID_CLASSES = {"ripe", "unripe", "freshripe", "freshunripe", "overripe", "rotten"}
    valid_detected = False

    if results.boxes:
        for box in results.boxes:
            cls_idx = int(box.cls.item())
            cls_name = model.names[cls_idx]
            if cls_name not in VALID_CLASSES:
                continue

            valid_detected = True
            conf = float(box.conf.item())
            x1, y1, x2, y2 = box.xyxy[0]
            bbox = {
                "x": round(x1.item() / MODEL_W, 4),
                "y": round(y1.item() / MODEL_H, 4),
                "width": round((x2 - x1).item() / MODEL_W, 4),
                "height": round((y2 - y1).item() / MODEL_H, 4),
            }
            analysis_results.append({
                "ripeness": KOREAN_CLASSES.get(cls_name, cls_name),
                "confidence": round(conf, 3),
                "freshness": round(FRESHNESS_MAP.get(cls_name, 0.0), 3),
                "boundingBox": bbox
            })
    return analysis_results if valid_detected else []

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
    verification_link = f"http://localhost:8000/verify/{token}"
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USER = "forgpt0405@gmail.com"
    SMTP_PASSWORD = "oxtf iqer cmuj klzr"  # Gmail 앱 비밀번호 사용 권장

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

def safe_decode_and_resize(img_bytes: bytes, dst_w: int = TARGET_W, dst_h: int = TARGET_H) -> np.ndarray:
    """빠른 디코딩 + 레터박스 (BGR 반환)"""
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR
    if img is None:
        raise ValueError("이미지 디코딩 실패")
    return letterbox_image(img, dst_w, dst_h)  # BGR

def create_analysis_video(current_user, task_id: str, frames_bgr: list[np.ndarray]):
    final_video_path = RESULTS_DIR / f"{task_id}_final.mp4"

    # (A) 상태 업데이트 헬퍼
    def set_task(status:str, **extra):
        tasks[task_id] = {**tasks.get(task_id, {}), "status": status, **extra}

    set_task("PROCESSING", result=None)
    print(f"[{task_id}] 비디오 생성 시작... (frames={len(frames_bgr)})")

    w, h = TARGET_W, TARGET_H

    # (B) 코덱 폴백 시도
    fourcc_candidates = ["avc1", "mp4v", "XVID", "MJPG"]
    writer = None
    for cc in fourcc_candidates:
        fourcc = cv2.VideoWriter_fourcc(*cc)
        wr = cv2.VideoWriter(str(final_video_path), fourcc, VIDEO_FPS, (w, h))
        if wr.isOpened():
            writer = wr
            print(f"[{task_id}] VideoWriter opened with codec={cc}")
            break
        else:
            wr.release()
    if writer is None:
        set_task("FAILURE", result="VideoWriter 초기화 실패(코덱)")
        print(f"[{task_id}] VideoWriter open failed for all codecs")
        return
    
    # YOLO warmup: 콜드스타트로 첫 프레임에서 버벅이는 것 방지
    if model:
        try:
            with torch.no_grad():
                _ = model(np.zeros((h, w, 3), dtype=np.uint8),
                          imgsz=(w, h), conf=0.25, verbose=False)
            print(f"[{task_id}] warmup done")
        except Exception as e:
            print(f"[{task_id}] warmup skip: {e}")

    # (C) 전체 타임아웃(예: 180초)
    deadline = time.time() + 180

    try:
        total_frames = int(len(frames_bgr) * SECONDS_PER_IMAGE * VIDEO_FPS)
        total_img_width = w * len(frames_bgr)
        infer_conf_list, ripeness_labels = [], []

        for i in range(total_frames):
            if time.time() > deadline:
                raise TimeoutError("비디오 생성 타임아웃")

            current_x = int((total_img_width - w) * (i / max(1, total_frames - 1)))
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            frame_x = 0
            for img in frames_bgr:
                img_start = frame_x - current_x
                img_end = (frame_x + w) - current_x
                if img_end > 0 and img_start < w:
                    src_start = max(0, -img_start)
                    src_end   = min(w, w - img_start)
                    dst_start = max(0, img_start)
                    dst_end   = min(w, img_end)
                    if src_end > src_start and dst_end > dst_start:
                        frame[:, dst_start:dst_end] = img[:, src_start:src_end]
                frame_x += w

            # 추론 간소화
            do_infer = model and (i % INFER_EVERY_N_FRAMES == 1) and i > 5
            if do_infer:
                with torch.no_grad():
                    results = model(frame, imgsz=(w, h), conf=0.25, verbose=False)
                if results and results[0].boxes is not None:
                    for box in results[0].boxes:
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = model.names[cls_id]
                        label_ko = KOREAN_CLASSES.get(cls_name, cls_name)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                        infer_conf_list.append(conf); ripeness_labels.append(label_ko)

            writer.write(frame)

            if i % 10 == 0:
                # 진행률 로그 (선택: 클라이언트에 progress도 내려주려면 tasks에 저장)
                print(f"[{task_id}] progress {i}/{total_frames}")

        writer.release(); writer = None

        # 생성 검증
        if not final_video_path.exists() or final_video_path.stat().st_size == 0:
            raise IOError("최종 MP4 파일이 비어 있음")

        # 결과 기록
        final_ripeness = Counter(ripeness_labels).most_common(1)[0][0] if ripeness_labels else "분석불가"
        freshness = LABEL_SCORE.get(final_ripeness, 0)
        avg_conf = round(sum(infer_conf_list) / len(infer_conf_list), 3) if infer_conf_list else 0.0

        # DB 저장
        db = SessionLocal()
        try:
            with open(final_video_path, "rb") as f:
                video_bytes = f.read()
            username = current_user.nickname if current_user else "unknown"
            db.add(Analysis(
                username=username, ripeness=final_ripeness, freshness=freshness,
                confidence=avg_conf, video_path=f"/results/{final_video_path.name}",
                video_blob=video_bytes, created_at=datetime.now(timezone("Asia/Seoul"))
            ))
            db.commit()
            update_daily_analysis_stat(db, datetime.now(timezone("Asia/Seoul")).date())
        finally:
            db.close()

        set_task("SUCCESS", result=f"/results/{final_video_path.name}")
        print(f"[{task_id}] ✅ 최종 비디오 생성 성공.")
    except Exception as e:
        set_task("FAILURE", result=str(e))
        print(f"[{task_id}] ❌ 비디오 생성 실패:", repr(e))
    finally:
        if writer is not None:
            writer.release()

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
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    )

# --- 분석 라우터 (모든 API에 인증 필요) ---
@analysis_router.post("/analyze")
async def analyze_single_image(payload: ImagePayload, current_user: User = Depends(get_current_user)):
    if not model:
        raise HTTPException(status_code=503, detail="모델이 현재 사용할 수 없습니다.")
    try:
        img_bytes = base64.b64decode(payload.image)
        # 1) 빠른 디코드 + 레터박스(동기 OK)
        img_bgr = safe_decode_and_resize(img_bytes, MODEL_W, MODEL_H)

        # 2) 추론만 스레드풀로
        loop = asyncio.get_running_loop()
        detections = await loop.run_in_executor(EXECUTOR, run_yolo_np_bgr, img_bgr)

        avg_conf = round((sum(d["confidence"] for d in detections) / len(detections)) if detections else 0.0, 4)
        avg_fresh = round((sum(d["freshness"] for d in detections) / len(detections)) if detections else 0.0, 4)

        # DB 저장(동일)
        db = SessionLocal()
        try:
            db.add(Analysis(
                username=current_user.nickname,
                ripeness=detections[0]["ripeness"] if detections else "분석불가",
                confidence=avg_conf, freshness=avg_fresh,
                image_blob=img_bytes, created_at=datetime.now(KST)
            ))
            db.commit()
            update_daily_analysis_stat(db, datetime.now(KST).date())
        finally:
            db.close()

        return {"detections": detections, "avg_confidence": avg_conf}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 분석 중 오류: {e}")

@analysis_router.post("/analyze_video")
async def start_video_analysis(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    if not files or len(files) < 1:
        raise HTTPException(status_code=400, detail="동영상 분석을 위해서는 1장 이상의 이미지가 필요합니다.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=413, detail=f"이미지는 최대 {MAX_FILES}장까지 업로드 가능합니다.")

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "PENDING", "result": None, "image_results": []}  # ← image_results 필드 유지

    images_for_video = []
    for f in files[:MAX_FILES]:
        content = await f.read()
        if not content:
            continue
        if len(content) > MAX_BYTES:
            # 클라이언트가 파일별 에러를 알 수 있게 큐에 남겨도 됨
            tasks[task_id]["image_results"].append({
                "filename": f.filename, "detections": [], "avg_confidence": 0,
                "error": f"파일 용량(최대 {MAX_BYTES//1024//1024}MB) 초과"
            })
            continue
        try:
            resized_bgr = safe_decode_and_resize(content, TARGET_W, TARGET_H)
            images_for_video.append(resized_bgr)
        except Exception as e:
            tasks[task_id]["image_results"].append({
                "filename": f.filename, "detections": [], "avg_confidence": 0, "error": str(e)
            })

    if images_for_video:
        threading.Thread(
            target=create_analysis_video, args=(current_user, task_id, images_for_video), daemon=True
        ).start()
    else:
        tasks[task_id] = {"status": "FAILURE", "result": "유효한 이미지가 없습니다.", "image_results": []}

    # ✅ 즉시 200 응답 (무거운 일은 스레드에서)
    return {"task_id": task_id, "results": tasks[task_id]["image_results"]}

# --- 작업 상태 확인 라우터 (인증 필요 없음) ---
@task_router.get("/{task_id}/status")
async def get_task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "status": task["status"],
        "result": task.get("result"),
        "image_results": task.get("image_results", [])
    }

# --- 통계 라우터 ---
@stats_router.get("/", response_model=dict)
def get_stats(db: Session = Depends(get_db)):
    today = datetime.now(KST).date()

    # ✅ 통계 테이블에서 오늘자 데이터 가져옴
    today_stat = db.query(DailyAnalysisStat).filter(DailyAnalysisStat.date == today).first()

    if not today_stat:
        # 통계가 없으면 0으로 리턴 (혹은 update_daily_analysis_stat() 호출도 가능)
        return {
            "todayAnalyses": 0,
            "avgRipeness": 0.0,
            "totalUploads": db.query(Analysis).count(),
            "ripeness_counts": {}
        }

    # ✅ 실시간 숙성도 분포만 analysis에서 구함 (도넛 차트용)
    start_dt = datetime.combine(today, dtime.min).astimezone(KST)
    end_dt = datetime.combine(today, dtime.max).astimezone(KST)

    ripeness_counts_query = (
        db.query(Analysis.ripeness, func.count(Analysis.id))
        .filter(
            Analysis.created_at >= start_dt,
            Analysis.created_at <= end_dt,
            Analysis.ripeness != "비디오분석"
        )
        .group_by(Analysis.ripeness)
        .all()
    )
    ripeness_counts = {ripeness: count for ripeness, count in ripeness_counts_query}

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

        # 숙성도 분포 쿼리
        start_dt = datetime.combine(today, dtime.min).astimezone(KST)
        end_dt = datetime.combine(today, dtime.max).astimezone(KST)

        ripeness_counts_query = (
            db.query(Analysis.ripeness, func.count(Analysis.id))
            .filter(
                Analysis.created_at >= start_dt,
                Analysis.created_at <= end_dt,
                Analysis.ripeness != "비디오분석"
            )
            .group_by(Analysis.ripeness)
            .all()
        )
        ripeness_counts = {r: c for r, c in ripeness_counts_query}

        # 어제까지 숙성 종류 수
        yest_end = datetime.combine(yesterday, dtime.max).astimezone(KST)
        ripeness_types_yesterday = db.query(func.count(func.distinct(Analysis.ripeness))).filter(
            Analysis.created_at <= yest_end
        ).scalar()

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
            "ripeness_counts": ripeness_counts,
            "ripeness_types_yesterday": ripeness_types_yesterday,
            "avg_confidence_today": acc_today,
            "avg_confidence_yesterday": acc_yest,
            "avg_freshness_today": fresh_today,
            "avg_freshness_yesterday": fresh_yest,
            "today_variety": today_stat.variety_count if today_stat else 0,
            "yesterday_variety": yest_stat.variety_count if yest_stat else 0,
        }

    except Exception as e:
        print(f"[❌ 에러 발생] {e}")
        raise
    finally:
        db.close()

# 앱 시작 시 자동 통계 갱신
@app.on_event("startup")
def generate_today_stats():
    db = SessionLocal()
    try:
        update_daily_analysis_stat(db, datetime.now(KST).date())
    finally:
        db.close()  

@app.get("/ping")
def ping():
    return {"ok": True}

# 서버 제한값을 환경변수화 + 프론트에 자동 전파
settings_router = APIRouter(tags=["Settings"])

def _int(name, default): return int(os.getenv(name, str(default)))
def _float(name, default): return float(os.getenv(name, str(default)))

@settings_router.get("/")
def get_settings():
    return {
        "MODEL_W": _int("MODEL_W", 640),
        "MODEL_H": _int("MODEL_H", 480),
        "MAX_FILES": _int("MAX_FILES", 20),          # 0이면 무제한으로 해석
        "MAX_BYTES": _int("MAX_BYTES", 10*1024*1024),# 0이면 무제한
        "VIDEO_FPS": _int("VIDEO_FPS", 8),
        "INFER_EVERY_N_FRAMES": _int("INFER_EVERY_N_FRAMES", 10),
        "SECONDS_PER_IMAGE": _float("SECONDS_PER_IMAGE", 1.0),
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