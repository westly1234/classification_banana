# --- 📁 backend/main.py ---

import base64, io, uuid, threading, time, smtplib, pytz, cv2, torch, numpy as np
from datetime import datetime, timedelta, date, time as dtime
from pytz import timezone
from pathlib import Path
from markupsafe import Markup
from PIL import Image, ImageFont, ImageDraw
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
from db import SessionLocal, init_db
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
SQLALCHEMY_DATABASE_URL = "sqlite:///./users.db?check_same_thread=False"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# --- 👤 사용자 모델 ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    nickname = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    is_verified = Column(Integer, default=0)  # 0 = 미인증, 1 = 인증완료
    is_superuser = Column(Boolean, default=False)

# --- 🍌 분석 결과 저장 모델 ---
class Analysis(Base):
    __tablename__ = "analysis"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String)
    ripeness = Column(String)
    freshness = Column(Float, nullable=True)
    confidence = Column(Float)
    image_path = Column(String, nullable=True)
    video_path = Column(String, nullable=True)
    image_blob = Column(LargeBinary, nullable=True)
    video_blob = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone("Asia/Seoul")))

Base.metadata.create_all(bind=engine)

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
# 프론트 주소(배포/로컬)
FRONT_URL = "https://classification-banana-2.onrender.com"

# (원하면 문서 숨김: docs_url=None, redoc_url=None)
app = FastAPI(title="바나나 YOLO 분석")

admin = Admin(app, engine, authentication_backend=SimpleAuth(secret_key=SECRET_KEY))
admin.add_view(UserAdmin)
admin.add_view(AnalysisAdmin)

# ✅ CORS: 프론트 도메인만 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONT_URL, "http://localhost:5173"],
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

# ✅ StaticFiles 서브앱에 CORS를 직접 적용
results_app = CORSMiddleware(
    app=StaticFiles(directory=RESULTS_DIR),
    allow_origins=[FRONT_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)
app.mount("/results", results_app, name="results")

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

def run_yolo_model(image: Image.Image):
    if not model:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="모델을 사용할 수 없습니다.")
    
    image = image.convert("RGB")
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    # ✅ Letterbox 적용 (YOLO 학습 해상도 기준)
    img_resized = letterbox_image(img_cv, 640, 480)

    # ✅ 모델 추론
    results = model(img_resized, imgsz=(640, 480), conf=0.1, verbose=False)[0]

    analysis_results = []
    VALID_CLASSES = {"ripe", "unripe", "freshripe", "freshunripe", "overripe", "rotten"}
    valid_detected = False

    if results.boxes:
        for box in results.boxes:
            cls_idx = int(box.cls.item())
            cls_name = model.names[cls_idx]

            # ✅ 바나나 관련 클래스만 필터링
            if cls_name not in VALID_CLASSES:
                continue

            valid_detected = True
            conf = float(box.conf.item())
            freshness = FRESHNESS_MAP.get(cls_name, 0.0)
            x1, y1, x2, y2 = box.xyxy[0]

            bbox = {
                "x": round(x1.item() / 640, 4),
                "y": round(y1.item() / 480, 4),
                "width": round((x2 - x1).item() / 640, 4),
                "height": round((y2 - y1).item() / 480, 4),
            }

            analysis_results.append({
                "ripeness": KOREAN_CLASSES.get(cls_name, cls_name),
                "confidence": round(conf, 3),
                "freshness": round(freshness, 3),
                "boundingBox": bbox
            })

    # ✅ 바나나 클래스가 하나도 없으면 빈 리스트 반환
    if not valid_detected:
        return []

    return analysis_results

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
@app.post("/signup")
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

@app.get("/verify/{token}")
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
@app.post("/login", response_model=Token)
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

# ===== 리소스 제한 =====
MAX_FILES = 5                 # 한 번에 최대 5장
MAX_BYTES = 2 * 1024 * 1024   # 각 파일 최대 2MB
TARGET_W, TARGET_H = 640, 480 # 작업 해상도
VIDEO_FPS = 12                # 낮은 FPS
SECONDS_PER_IMAGE = 1.5       # 이미지 당 체류 시간
INFER_EVERY_N_FRAMES = 2      # 2프레임에 한 번만 YOLO 추론

def safe_decode_and_resize(img_bytes: bytes, dst_w: int = TARGET_W, dst_h: int = TARGET_H) -> np.ndarray:
    """이미지를 안전하게 열고 (RGB) 640x480으로 리사이즈 + letterbox."""
    pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    arr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return letterbox_image(arr, dst_w, dst_h)

def create_analysis_video(current_user, task_id: str, frames_bgr: list[np.ndarray]):
    """
    frames_bgr: 이미 TARGET_W x TARGET_H 로 letterbox된 BGR 프레임 목록
    OpenCV로 바로 mp4 파일 생성 (mp4v). 프레임 간격 샘플링으로 YOLO 부하 감소.
    """
    final_video_path = RESULTS_DIR / f"{task_id}_final.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # 브라우저 재생 가능(대부분)
    writer = None
    db = SessionLocal()

    try:
        tasks[task_id] = {"status": "PROCESSING", "result": None}
        print(f"[{task_id}] 비디오 생성 시작... (frames={len(frames_bgr)})")

        w, h = TARGET_W, TARGET_H
        writer = cv2.VideoWriter(str(final_video_path), fourcc, VIDEO_FPS, (w, h))
        if not writer.isOpened():
            raise IOError("VideoWriter 초기화 실패")

        # 총 프레임 수 계산
        total_frames = int(len(frames_bgr) * SECONDS_PER_IMAGE * VIDEO_FPS)

        # 프레임 스트림 만들기(가로 스크롤 효과 그대로 유지)
        total_img_width = w * len(frames_bgr)
        infer_conf_list, ripeness_labels = [], []

        for i in range(total_frames):
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

            # 🔻 부하 절감: N프레임마다만 추론
            if model and (i % INFER_EVERY_N_FRAMES == 0):
                try:
                    with torch.no_grad():
                        results = model(frame, verbose=False)
                    for box in results[0].boxes:
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = model.names[cls_id]
                        label_ko = KOREAN_CLASSES.get(cls_name, cls_name)

                        # 박스 & 라벨
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                        try:
                            pil_frame = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                            draw = ImageDraw.Draw(pil_frame, "RGBA")
                            # 폰트가 없으면 기본폰트 fallback
                            try:
                                font = ImageFont.truetype("fonts/NanumGothic.ttf", 20)
                            except Exception:
                                font = ImageFont.load_default()
                            text = f"{label_ko} {conf:.2f}"
                            tw, th = draw.textlength(text, font=font), 18
                            ty = max(0, y1 - th - 4)
                            draw.rectangle([(x1, ty), (x1 + int(tw) + 6, ty + th + 6)], fill=(0,0,0,160))
                            draw.text((x1 + 3, ty + 3), text, font=font, fill=(255,255,255,255))
                            frame = cv2.cvtColor(np.array(pil_frame), cv2.COLOR_RGB2BGR)
                        except Exception:
                            pass

                        infer_conf_list.append(conf)
                        ripeness_labels.append(label_ko)
                except Exception as e:
                    # 추론 실패해도 프레임은 계속 작성
                    print(f"[{task_id}] 추론 스킵: {e}")

            writer.write(frame)

        writer.release(); writer = None

        if not final_video_path.exists() or final_video_path.stat().st_size == 0:
            raise IOError("최종 MP4 파일이 생성되지 않았거나 비어 있음.")

        tasks[task_id] = {"status": "SUCCESS", "result": f"/results/{final_video_path.name}"}
        print(f"[{task_id}] ✅ 최종 비디오 생성 성공.")

        # 통계/DB 기록
        if ripeness_labels:
            final_ripeness = Counter(ripeness_labels).most_common(1)[0][0]
        else:
            final_ripeness = "분석불가"
        freshness = LABEL_SCORE.get(final_ripeness, 0)
        avg_conf = round(sum(infer_conf_list) / len(infer_conf_list), 3) if infer_conf_list else 0.0

        with open(final_video_path, "rb") as f:
            video_bytes = f.read()

        try:
            username = current_user.nickname if current_user else "unknown"
            db.add(Analysis(
                username=username,
                ripeness=final_ripeness,
                freshness=freshness,
                confidence=avg_conf,
                video_path=f"/results/{final_video_path.name}",
                video_blob=video_bytes,
                created_at=datetime.now(timezone("Asia/Seoul"))
            ))
            db.commit()
            today = datetime.now(timezone("Asia/Seoul")).date()
            update_daily_analysis_stat(db, today)
        finally:
            db.close()

    except Exception as e:
        tasks[task_id] = {"status": "FAILURE", "result": str(e)}
        print(f"[{task_id}] ❌ 비디오 생성 실패: {e}")
    finally:
        if writer is not None:
            writer.release()

# --- 동영상 스트리밍 함수 ---
@app.get("/results/{filename}")
async def get_video(filename: str):
    file_path = RESULTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        file_path,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    )

# --- 📍 라우터 분리 ---
auth_router = APIRouter(tags=["Authentication"])
analysis_router = APIRouter(tags=["Analysis"], dependencies=[Depends(get_current_user)])
task_router = APIRouter(tags=["Tasks"])
stats_router = APIRouter(tags=["Statistics"])

# --- 분석 라우터 (모든 API에 인증 필요) ---
@analysis_router.post("/analyze")
def analyze_single_image(payload: ImagePayload, current_user: User = Depends(get_current_user)):
    if not model:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="모델이 현재 사용할 수 없습니다.")
    try:
        image_data = base64.b64decode(payload.image)
        resized_bgr = safe_decode_and_resize(image_data, TARGET_W, TARGET_H)
        image = Image.fromarray(cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2RGB))
        detections = run_yolo_model(image)

        # ✅ 평균 신뢰도 계산
        avg_conf = sum([d["confidence"] for d in detections]) / len(detections) if detections else 0
        avg_fresh = sum([d["freshness"] for d in detections]) / len(detections) if detections else 0

        db = SessionLocal()
        try:
            db.add(Analysis(
                username=current_user.nickname,
                ripeness=detections[0]["ripeness"] if detections else "분석불가",
                confidence=avg_conf,
                freshness=avg_fresh, 
                image_blob=image_data,
                created_at=datetime.now(KST)
            ))
            db.commit()
            today = datetime.now(KST).date()
            update_daily_analysis_stat(db, today)
        finally:
            db.close()

        if len(detections) > 0:
            avg_conf = sum([d["confidence"] for d in detections]) / len(detections)

        return {
            "detections": detections,
            "avg_confidence": round(avg_conf, 4)  # 백엔드에서 미리 계산
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"이미지 분석 중 오류 발생: {e}")

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
    tasks[task_id] = {"status": "PENDING", "result": None}

    images_for_video, image_results = [], []
    for f in files[:MAX_FILES]:
        content = await f.read()
        if not content:
            continue
        if len(content) > MAX_BYTES:
            image_results.append({
                "filename": f.filename, "detections": [], "avg_confidence": 0,
                "error": f"파일 용량(최대 {MAX_BYTES//1024//1024}MB) 초과"
            })
            continue

        # 분석용 리사이즈 이미지 한 벌 (가볍게)
        try:
            resized_bgr = safe_decode_and_resize(content, TARGET_W, TARGET_H)
            images_for_video.append(resized_bgr)   # ✅ 이미 numpy(BGR)로 보관
        except Exception as e:
            image_results.append({"filename": f.filename, "detections": [], "avg_confidence": 0, "error": str(e)})
            continue

        # 즉시 1장 분석
        try:
            pil_image = Image.fromarray(cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2RGB))
            detections = run_yolo_model(pil_image)
            avg_conf = sum(d["confidence"] for d in detections) / len(detections) if detections else 0
            avg_fresh = sum(d["freshness"] for d in detections) / len(detections) if detections else 0

            db = SessionLocal()
            try:
                db.add(Analysis(
                    username=current_user.nickname,
                    ripeness=detections[0]["ripeness"] if detections else "분석불가",
                    confidence=avg_conf,
                    freshness=avg_fresh,
                    image_blob=None,  # 굳이 bytes 저장 안함 → DB 부하 감소
                    created_at=datetime.now(KST)
                ))
                db.commit()
            finally:
                db.close()

            image_results.append({
                "filename": f.filename,
                "detections": detections,
                "avg_confidence": avg_conf
            })
        except Exception as e:
            image_results.append({
                "filename": f.filename, "detections": [], "avg_confidence": 0, "error": str(e)
            })

    if images_for_video:
        thread = threading.Thread(target=create_analysis_video, args=(current_user, task_id, images_for_video))
        thread.start()
    else:
        tasks[task_id] = {"status": "FAILURE", "result": "유효한 이미지가 없습니다."}

    return {"task_id": task_id, "results": image_results}

# --- 작업 상태 확인 라우터 (인증 필요 없음) ---
@task_router.get("/tasks/{task_id}/status")
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
@stats_router.get("/stats", response_model=dict)
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

@stats_router.get("/stats/daily")
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

@stats_router.get("/stats/summary")
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

# --- 최종 라우터 등록 ---
app.include_router(auth_router) # @app.post('/login') 등을 여기에 포함시키려면 auth_router로 변경해야 함
app.include_router(analysis_router)
app.include_router(task_router)
app.include_router(stats_router)

# --- ✅ 루트 확인용 ---
@app.get("/")
def root():
    return {"message": "🍌 바나나 YOLO 분석 서버 작동 중"}