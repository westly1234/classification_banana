# --- 📁 backend/main.py ---

import os, asyncio, concurrent.futures, base64, uuid, threading, math, json, time, smtplib, pytz, cv2, torch, subprocess, shutil, numpy as np
from datetime import datetime, timedelta, date, time as dtime
from pytz import timezone
from pathlib import Path
from markupsafe import Markup
from PIL import Image, ImageDraw, ImageFont, ImageFile
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
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from typing import List, Tuple

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
from models import User, Analysis, DailyAnalysisStat, TaskStatus

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

# 전역 설정(중복 없이 한 번만 정의)
def _int(name, default): return int(os.getenv(name, str(default)))
def _float(name, default): return float(os.getenv(name, str(default)))

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
FRONT_REGEX = r"^https://classification-banana.*\.onrender\.com$"
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

# --- YOLO 로드 ---
BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "best.pt"

# 3-1) 전역 상태
model = None
MODEL_READY = False
DB_READY = False

# 3-2) 무거운 초기화 함수
def _heavy_init():
    global model, MODEL_READY, DB_READY
    try:
        init_db()
        DB_READY = True
        print("✅ DB init done")
    except Exception as e:
        print("❌ DB init failed:", e)

    try:
        m = YOLO(MODEL_PATH)
        m.fuse()                    # ✅ Conv+BN fuse -> CPU에서 이득
        m.to('cpu')                 # 혹시 모를 디바이스 이동 방지
        globals()["model"] = m
        MODEL_READY = True
        print("✅ YOLO loaded")
    except Exception as e:
        print("❌ YOLO load failed:", e)

    # ✅ 준비 끝난 뒤 통계 1회 갱신
    try:
        db = SessionLocal()
        update_daily_analysis_stat(db, datetime.now(KST).date())
    except Exception as e:
        print("❌ update_daily_analysis_stat at startup:", e)
    finally:
        db.close()

# 3-3) 스타트업에서 비동기 시작
@app.on_event("startup")
def startup():
    threading.Thread(target=_heavy_init, daemon=True).start()

# 3-4) 헬스체크는 즉시 200
@app.get("/ping")
def ping():
    return {"ok": True, "model": MODEL_READY, "db": DB_READY}

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

# 감지 파라미터
QUICK_IMGSZ = int(os.getenv("QUICK_IMGSZ", "512"))
FINAL_IMGSZ = int(os.getenv("FINAL_IMGSZ", "640"))
QUICK_CONF  = float(os.getenv("QUICK_CONF",  "0.25"))
FINAL_CONF  = float(os.getenv("FINAL_CONF",  "0.10"))
MAX_DET     = int(os.getenv("MAX_DET",      "3"))

# 팬(스크롤) 느낌
PAN_PX_PER_SEC = int(os.getenv("PAN_PX_PER_SEC", "120"))  # 초당 이동 픽셀
HOLD_SEC_PER_IMG = float(os.getenv("HOLD_SEC_PER_IMG", "2.0"))  # 한 장당 최소 체류

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

def run_yolo_np_bgr(img_bgr: np.ndarray, imgsz=None, conf=None, max_det=None):
    if not model:
        raise HTTPException(status_code=503, detail="모델을 사용할 수 없습니다.")

    h, w = img_bgr.shape[:2]
    imgsz = imgsz or (w, h)
    res = model(img_bgr, imgsz=imgsz, conf=(conf or 0.1),
                max_det=(max_det or 100), verbose=False)[0]

    out = []
    VALID = {"ripe","unripe","freshripe","freshunripe","overripe","rotten"}
    for box in (res.boxes or []):
        cls = model.names[int(box.cls.item())]
        if cls not in VALID: 
            continue
        x1,y1,x2,y2 = box.xyxy[0]
        out.append({
            "ripeness": KOREAN_CLASSES.get(cls, cls),
            "confidence": float(box.conf.item()),
            "freshness": round(FRESHNESS_MAP.get(cls, 0.0), 3),
            "boundingBox": {
                "x": round(x1.item()/w,4), "y": round(y1.item()/h,4),
                "width": round((x2-x1).item()/w,4), "height": round((y2-y1).item()/h,4),
            },
        })
    return out

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
def safe_decode_and_resize(img_bytes: bytes, dst_w: int = TARGET_W, dst_h: int = TARGET_H) -> np.ndarray:
    """빠른 디코딩 + 레터박스 (BGR 반환)"""
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR
    if img is None:
        raise ValueError("이미지 디코딩 실패")
    return letterbox_image(img, dst_w, dst_h)  # BGR

VIDEO_FPS = _int("VIDEO_FPS", 8)
HOLD_SEC  = _float("SECONDS_PER_IMAGE", 1.0)
# ---------------------------
# 오버레이(박스/라벨) 그리기
# ---------------------------
def draw_overlay(frame_bgr: np.ndarray, detections: list, w: int, h: int) -> None:
    """
    detections: [{boundingBox:{x,y,width,height}, ripeness, confidence}, ...]
    좌표는 0~1 정규화.
    박스는 OpenCV, 라벨은 PIL+TTF(한글)로 그립니다.
    """
    if not detections:
        return

    # 1) 먼저 박스 (OpenCV)
    for d in detections:
        bb = (d.get("boundingBox") or {})
        x1 = int((bb.get("x", 0.0)) * w)
        y1 = int((bb.get("y", 0.0)) * h)
        x2 = int((bb.get("x", 0.0) + bb.get("width", 0.0)) * w)
        y2 = int((bb.get("y", 0.0) + bb.get("height", 0.0)) * h)

        # 경계 클램프
        x1 = max(0, min(w - 1, x1))
        y1 = max(0, min(h - 1, y1))
        x2 = max(x1 + 1, min(w, x2))
        y2 = max(y1 + 1, min(h, y2))

        cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 255), 3)

    # 2) 라벨 (PIL + 한글 폰트)
    #    RGBA로 변환해서 반투명 배경을 올린 뒤 다시 BGR로 되돌립니다.
    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    draw = ImageDraw.Draw(img)
    font = _get_font(22)  # <- 너가 만든 폰트 캐시 함수 사용

    for d in detections:
        bb = (d.get("boundingBox") or {})
        x1 = int((bb.get("x", 0.0)) * w)
        y1 = int((bb.get("y", 0.0)) * h)

        ripeness = d.get("ripeness", "")
        conf_pct = float(d.get("confidence", 0.0)) * 100.0
        label = f"{ripeness} {conf_pct:.1f}%"

        # 텍스트 크기
        l, t, r, b = draw.textbbox((0, 0), label, font=font)
        tw, th = (r - l), (b - t)

        pad = 6
        box_w = tw + pad * 2
        box_h = th + pad * 2

        # 박스가 프레임을 넘지 않도록 시작점(x, y_top) 재조정
        x = max(0, min(w - box_w, x1))
        y_top = max(0, y1 - box_h - 2)  # 텍스트 박스는 박스 위쪽에

        # 반투명 배경
        bg = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 210))
        img.paste(bg, (x, y_top), bg)  # mask로 알파 사용

        # 텍스트
        draw.text((x + pad, y_top + pad), label, font=font, fill=(255, 255, 255, 255))

    # 3) 되돌리기 (in-place 갱신)
    frame_bgr[:] = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        
# ---------------------------------------
# 비디오 작성: 좌→우 패닝(확대 + 이동)으로 실시간 스캔 느낌
# ---------------------------------------
def _pad_sides(img_bgr: np.ndarray, pad: int = 12) -> np.ndarray:
    return cv2.copyMakeBorder(img_bgr, 0, 0, pad, pad, cv2.BORDER_CONSTANT, value=(0,0,0))

def make_long_strip(frames_with_dets: List[Tuple[np.ndarray, list]], out_w: int, out_h: int) -> np.ndarray:
    """
    각 프레임에 라벨을 그리고(한글), 좌우 패딩 후 가로로 연결.
    결과 long_img.shape == (out_h, out_w * N + padding*2*N, 3)
    """
    tiles = []
    for img_bgr, dets in frames_with_dets:
        h, w = img_bgr.shape[:2]
        # 안전: 사이즈 불일치 시 리사이즈
        if (w, h) != (out_w, out_h):
            img_bgr = cv2.resize(img_bgr, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        # 오버레이
        canvas = img_bgr.copy()
        draw_overlay(canvas, dets, out_w, out_h)
        # 좌우 패딩 후 추가
        tiles.append(_pad_sides(canvas, pad=12))

    long_img = np.hstack(tiles) if tiles else np.zeros((out_h, out_w, 3), dtype=np.uint8)
    return long_img

def write_video(
    frames_with_dets: List[Tuple[np.ndarray, list]],
    out_path: str,
    fps: int = VIDEO_FPS,              # 예: 8
    hold_sec: float = SECONDS_PER_IMAGE  # 이미지 1장 당 보여줄 시간(초)
) -> None:
    """
    1) 모든 이미지를 (TARGET_W, TARGET_H)로 맞춘 타일로 만들고 라벨을 그린 뒤,
    2) 가로로 이어붙여 long_img 생성,
    3) long_img를 좌→우로 일정 속도로 스크롤하면서 비디오 생성.
    """
    if not frames_with_dets:
        raise ValueError("frames_with_dets is empty")

    out_w = TARGET_W
    out_h = TARGET_H

    long_img = make_long_strip(frames_with_dets, out_w, out_h)
    H, L = long_img.shape[0], long_img.shape[1]
    if L <= out_w:
        # 이동 여지가 없으면 그냥 정지 비디오
        scroll_frames = max(1, int(math.ceil(hold_sec * fps)))
        frames = [long_img[:, 0:out_w]] * scroll_frames * len(frames_with_dets)
    else:
        # 전체 스크롤 프레임 수 = 이미지 수 * (hold_sec * fps)
        total_frames = max(1, int(math.ceil(len(frames_with_dets) * hold_sec * fps)))
        frames = []
        for i in range(total_frames):
            t = i / (total_frames - 1) if total_frames > 1 else 0.0  # 0→1
            dx = int(round(t * (L - out_w)))  # 왼→오
            crop = long_img[:, dx:dx + out_w]
            if crop.shape[1] < out_w:
                # 우측 끝에서 부족하면 패딩
                pad = out_w - crop.shape[1]
                crop = cv2.copyMakeBorder(crop, 0, 0, 0, pad, cv2.BORDER_CONSTANT, value=(0,0,0))
            frames.append(crop)

    # FFmpeg 파이프 우선
    using_ffmpeg = False
    proc = None
    vw = None
    if shutil.which("ffmpeg"):
        try:
            cmd = [
                "ffmpeg","-y","-loglevel","error",
                "-f","rawvideo","-pix_fmt","bgr24",
                "-s", f"{out_w}x{out_h}",
                "-r", str(fps), "-i","-",
                "-c:v","libx264","-preset","veryfast","-crf","23",
                "-pix_fmt","yuv420p","-movflags","+faststart",
                out_path
            ]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if proc.stdin is None:
                raise RuntimeError("failed to open ffmpeg stdin")
            using_ffmpeg = True
        except Exception as e:
            print(f"[write_video] ffmpeg open failed: {e}; fallback to OpenCV")

    if not using_ffmpeg:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        vw = cv2.VideoWriter(out_path, fourcc, fps, (out_w, out_h))
        if not vw.isOpened():
            raise RuntimeError(f"OpenCV VideoWriter open failed ({out_w}x{out_h}@{fps})")

    try:
        for i, fr in enumerate(frames):
            if using_ffmpeg:
                proc.stdin.write(fr.tobytes())
            else:
                vw.write(fr)
            if i % 10 == 0:
                print(f"[write_video] frame {i+1}/{len(frames)}")
    finally:
        if using_ffmpeg:
            try: proc.stdin.close()
            except Exception: pass
            rc = proc.wait(timeout=30)
            if rc != 0:
                raise RuntimeError(f"ffmpeg exited with code {rc}")
        elif vw is not None:
            vw.release()

# -------------------------------------------------------
# create_analysis_video (DB 저장까지 포함한 완전판 함수)
# -------------------------------------------------------
def create_analysis_video(
    current_user,
    task_id: str,
    frames_with_dets: List[Tuple[np.ndarray, list]],
) -> None:
    final_video_path = RESULTS_DIR / f"{task_id}_final.mp4"

    db = SessionLocal()
    try:
        set_task_db(db, task_id, status="PROCESSING", result=None)
    finally:
        db.close()
    print(f"[{task_id}] 비디오 생성 시작... (frames={len(frames_with_dets)})")

    try:
        write_video(frames_with_dets, str(final_video_path), fps=VIDEO_FPS, hold_sec=HOLD_SEC)

        if not final_video_path.exists() or final_video_path.stat().st_size == 0:
            raise IOError("최종 MP4 파일이 비어 있음")

        all_dets = [d for _, dets in frames_with_dets for d in dets]
        avg_conf = round(sum(d.get("confidence", 0.0) for d in all_dets) / len(all_dets), 3) if all_dets else 0.0
        labels   = [d.get("ripeness", "분석불가") for d in all_dets]
        final_ripeness = Counter(labels).most_common(1)[0][0] if labels else "분석불가"
        freshness = LABEL_SCORE.get(final_ripeness, 0.0)

        db = SessionLocal()
        try:
            username = getattr(current_user, "nickname", None) or "unknown"
            db.add(Analysis(
                username=username,
                ripeness=final_ripeness,
                confidence=avg_conf,
                freshness=freshness,
                video_path=f"/results/{final_video_path.name}",
                video_blob=None,
                created_at=datetime.now(timezone("Asia/Seoul")),
            ))
            db.commit()
            update_daily_analysis_stat(db, datetime.now(timezone("Asia/Seoul")).date())
        finally:
            db.close()

        db = SessionLocal()
        try:
            set_task_db(db, task_id, status="SUCCESS", result=f"/results/{final_video_path.name}")
        finally:
            db.close()
    except Exception as e:
        db = SessionLocal()
        try:
            set_task_db(db, task_id, status="FAILURE", result=str(e))
        finally:
            db.close()
        print(f"[{task_id}] ❌ 비디오 생성 실패:", repr(e))

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

# 상단에 한 줄
FAST_PREVIEW = 2   # 앞의 N장만 즉시 추론 (0~2 추천)

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
        # 상태를 먼저 생성
        set_task_db(db, task_id, status="PENDING", result=None, image_results=[])

    loop = asyncio.get_running_loop()

    # 1) 업로드 파일들 디코드만 먼저(가볍고 빠르게)
    decoded: list[tuple[str, np.ndarray]] = []   # [(filename, bgr)]
    image_results: list[dict] = []               # 프런트에 내려줄 썸네일 상태

    for f in files[:MAX_FILES]:
        content = await f.read()
        if not content:
            continue
        if MAX_BYTES and len(content) > MAX_BYTES:
            image_results.append({
                "filename": f.filename, "detections": [], "avg_confidence": 0,
                "error": f"파일 용량(최대 {MAX_BYTES//1024//1024}MB) 초과"
            })
            continue

        try:
            bgr = await loop.run_in_executor(EXECUTOR, safe_decode_and_resize, content, TARGET_W, TARGET_H)
            decoded.append((f.filename, bgr))
        except Exception as e:
            image_results.append({"filename": f.filename, "detections": [], "avg_confidence": 0, "error": str(e)})

    # 유효 이미지가 하나도 없으면 종료
    if len(decoded) == 0 and all(len(r.get("detections", [])) == 0 for r in image_results):
        with SessionLocal() as db:
            set_task_db(db, task_id, status="FAILURE", result="유효한 이미지가 없습니다.", image_results=image_results)
        return {"task_id": task_id, "results": image_results}

    # 2) 앞의 FAST_PREVIEW 장만 즉시 감지하여 바로 표시
    for idx, (fname, bgr) in enumerate(decoded):
        if idx < FAST_PREVIEW:
            dets = await loop.run_in_executor(EXECUTOR, run_yolo_np_bgr, bgr)
            avg_conf = round(sum(d["confidence"] for d in dets) / len(dets), 4) if dets else 0.0
            image_results.append({"filename": fname, "detections": dets, "avg_confidence": avg_conf})
        else:
            # 아직 미처리 → 빈 결과로 자리만 잡아둠(프런트는 이게 추후 채워지는 걸 폴링으로 받음)
            image_results.append({"filename": fname, "detections": [], "avg_confidence": 0})

    # 초기 썸네일 상태 저장 + 상태를 PROCESSING 으로 전환
    with SessionLocal() as db:
        set_task_db(db, task_id, status="PROCESSING", image_results=image_results)

    # 3) 백그라운드: 나머지 프레임을 하나씩 감지하면서 DB에 "점진 갱신" + 마지막에 비디오 생성
    def bg_finish_and_render():
        try:
            # 파일명 기준으로 결과를 빠르게 찾기 위해 map 구성
            # (주의: 최종 image_results 정렬은 decoded 순서를 유지)
            name_to_result = {r["filename"]: r for r in image_results}

            # 이미 처리된 FAST_PREVIEW는 그대로 두고, 나머지 이미지만 순차 감지
            for idx, (fname, bgr) in enumerate(decoded):
                if name_to_result.get(fname, {}).get("detections"):
                    continue  # 이미 채워진 썸네일(FAST_PREVIEW)

                dets = run_yolo_np_bgr(bgr)  # CPU 1코어 환경에선 순차가 가장 안정적
                avg_conf = round(sum(d["confidence"] for d in dets) / len(dets), 4) if dets else 0.0

                # 현재 항목 갱신
                name_to_result[fname] = {
                    "filename": fname,
                    "detections": dets,
                    "avg_confidence": avg_conf
                }

                # 🔁 여기서 "증분 저장" — 프런트 폴링이 있으면 썸네일이 한 장씩 채워짐
                with SessionLocal() as db:
                    # decoded 순서로 다시 리스트 구성(정렬 보장)
                    sorted_results = [name_to_result[p] for p, _ in decoded]
                    set_task_db(db, task_id, status="PROCESSING", image_results=sorted_results)

            # 모두 끝났으면 같은 순서로 frames_with_dets 생성
            filled: list[tuple[np.ndarray, list]] = []
            for fname, bgr in decoded:
                dets = name_to_result[fname]["detections"]
                filled.append((bgr, dets))

            # 비디오 생성(이 함수 안에서 상태 SUCCESS/FAILURE 업데이트)
            create_analysis_video(current_user, task_id, filled)

        except Exception as e:
            with SessionLocal() as db:
                set_task_db(db, task_id, status="FAILURE", result=str(e))

    threading.Thread(target=bg_finish_and_render, daemon=True).start()

    # 클라이언트는 task_id 로 폴링
    return {"task_id": task_id, "results": image_results}

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

    result = task.get("result")  # 보통 "/results/xxx.mp4"
    absolute_result = None

    if isinstance(result, str):
        # 이미 절대 URL이면 그대로 사용
        if result.startswith("http://") or result.startswith("https://"):
            absolute_result = result
        elif result.startswith("/"):
            # 프록시 헤더에서 첫 값 사용
            proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
            host  = (request.headers.get("x-forwarded-host")  or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
            absolute_result = f"{proto}://{host}{result}"

    return {
        "status": task.get("status"),
        "result": result,                 # 상대 경로 유지
        "absolute_result": absolute_result,  # 프런트는 이걸 우선 사용
        "image_results": task.get("image_results", []),
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

# 서버 제한값을 환경변수화 + 프론트에 자동 전파

def _int(name, default): return int(os.getenv(name, str(default)))
def _float(name, default): return float(os.getenv(name, str(default)))

@settings_router.get("/")
def get_settings():
    return {
        "MODEL_W": _int("MODEL_W", 640),
        "MODEL_H": _int("MODEL_H", 480),
        "MAX_FILES": _int("MAX_FILES", 20),
        "MAX_BYTES": _int("MAX_BYTES", 10*1024*1024),
        "VIDEO_FPS": VIDEO_FPS,          # ← 변수 사용
        "INFER_EVERY_N_FRAMES": _int("INFER_EVERY_N_FRAMES", 10),
        "SECONDS_PER_IMAGE": HOLD_SEC,   # ← 변수 사용
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