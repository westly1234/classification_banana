# --- 📁 backend/main.py ---

import base64, io, uuid, threading, time, smtplib, pytz, cv2, subprocess, numpy as np
from datetime import datetime, timedelta, date, time as dtime
from pytz import timezone
from pathlib import Path
from markupsafe import Markup
from PIL import Image, ImageFont, ImageDraw
from collections import defaultdict, Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# FastAPI 및 관련 라이브러리
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Request, status, Header, UploadFile, File, BackgroundTasks
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
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, func, LargeBinary, and_
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
app = FastAPI(title="바나나 YOLO 분석")

admin = Admin(app, engine, authentication_backend=SimpleAuth(secret_key=SECRET_KEY))
admin.add_view(UserAdmin)
admin.add_view(AnalysisAdmin)

origins = ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# 동영상 임시 저장 폴더 설정 (한 번만 선언)
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
app.mount("/results", StaticFiles(directory=RESULTS_DIR), name="results")

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
MODEL_PATH = BASE_DIR / "best (2).pt"

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
    # ✅ PIL → OpenCV 변환
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    # ✅ Letterbox 적용 (YOLO 학습 해상도 기준)
    img_resized = letterbox_image(img_cv, 640, 480)

    # ✅ 모델 추론
    results = model(img_resized, imgsz=(640, 480), conf=0.1, verbose=False)[0]

    analysis_results = []
    VALID_CLASSES = {"ripe", "unripe", "freshripe", "freshunripe", "overripe", "rotten"}

    if results.boxes:
        for box in results.boxes:
            cls_name = model.names[int(box.cls.item())]
            if cls_name in VALID_CLASSES:
                conf = float(box.conf.item())
                freshness = FRESHNESS_MAP.get(cls_name, 0.0)
                x1, y1, x2, y2 = box.xyxy[0]
                bbox = {
                    "x": round(x1.item() / 640, 4),  # 정규화 기준: letterbox 기준 해상도
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
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="잘못된 로그인 정보입니다.")
    if user.is_verified == 0:
        raise HTTPException(status_code=403, detail="이메일 인증 후 로그인 가능합니다.")
    access_token = jwt.encode({"sub": user.email, "nickname": user.nickname}, SECRET_KEY, algorithm=ALGORITHM)
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

def create_analysis_video(current_user, task_id: str, image_data_list: list):
    """
    여러 이미지를 받아 스크롤링 분석 비디오를 생성하고 모델 결과를 시각화.
    최종 출력은 웹 브라우저에서 재생 가능한 MP4(H.264 + yuv420p)로 저장됨.
    """
    intermediate_video_path = RESULTS_DIR / f"{task_id}_intermediate.avi"
    final_avi_path = RESULTS_DIR / f"{task_id}_final.avi"
    final_video_path = RESULTS_DIR / f"{task_id}_final.mp4"

    video_writer, cap, final_writer = None, None, None

    db = SessionLocal()
    try:
        tasks[task_id] = {"status": "PROCESSING", "result": None}
        print(f"[{task_id}] 비디오 생성 시작...")

        output_width, output_height, fps = 640, 480, 15

        # 1) 이미지 디코딩 및 검증
        valid_imgs = []
        for index, img_data in enumerate(image_data_list):
            try:
                pil_image = Image.open(io.BytesIO(img_data)).convert("RGB")  # ✅ 바로 열기
                cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                valid_imgs.append(letterbox_image(cv_image, output_width, output_height))
            except Exception as img_err:
                print(f"[{task_id}] 경고: {index+1}번째 이미지 처리 실패 → 건너뜀. 오류: {img_err}")
                continue

        if len(valid_imgs) < 1:
            raise ValueError("비디오 생성을 위한 유효한 이미지가 없습니다.")

        total_img_width = output_width * len(valid_imgs)

        # 2) 중간 비디오 생성
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        video_writer = cv2.VideoWriter(str(intermediate_video_path), fourcc, fps, (output_width, output_height))

        SECONDS_PER_IMAGE = 3
        fps = 15
        
        video_duration = len(valid_imgs) * SECONDS_PER_IMAGE
        total_frames = int(fps * video_duration)
        for i in range(total_frames):
            current_x = int((total_img_width - output_width) * (i / (total_frames - 1)))
            frame = np.zeros((output_height, output_width, 3), dtype=np.uint8)
            frame_x = 0
            for img in valid_imgs:
                img_resized = letterbox_image(img, output_width, output_height)
                img_start = frame_x - current_x
                img_end = (frame_x + output_width) - current_x
                if img_end > 0 and img_start < output_width:
                    src_start = max(0, -img_start)
                    src_end = min(output_width, output_width - img_start)
                    dst_start = max(0, img_start)
                    dst_end = min(output_width, img_end)
                    if src_end > src_start and dst_end > dst_start:
                        frame[:, dst_start:dst_end] = img_resized[:, src_start:src_end]
                frame_x += output_width
            video_writer.write(frame)
        video_writer.release()
        video_writer = None
        time.sleep(0.5)

        # 3) 모델 결과를 입힌 최종 AVI 생성
        cap = cv2.VideoCapture(str(intermediate_video_path))
        if not cap.isOpened():
            raise IOError("중간 비디오 파일을 열 수 없습니다.")

        final_writer = cv2.VideoWriter(str(final_avi_path), fourcc, fps, (output_width, output_height))
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if model:
                results = model(frame, verbose=False)
                for box in results[0].boxes:
                    x1, y1, x2, y2 = [int(i) for i in box.xyxy[0]]
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = KOREAN_CLASSES.get(model.names[cls_id], model.names[cls_id])
                    label = f"{cls_name} {conf:.2f}"

                    # ✅ 노란색 박스
                    color = (0, 255, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)

                    # ✅ Pillow로 반투명 검정 + 흰 글씨
                    pil_frame = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    draw = ImageDraw.Draw(pil_frame, "RGBA")
                    font = ImageFont.truetype("fonts/NanumGothic.ttf", 24)

                    text_bbox = draw.textbbox((0, 0), label, font=font)
                    text_w = text_bbox[2] - text_bbox[0]
                    text_h = text_bbox[3] - text_bbox[1]

                    # y좌표 보정
                    text_y = y1 - text_h - 8
                    if text_y < 0:
                        text_y = y1 + 5  # 텍스트를 박스 아래쪽으로 그리기

                    draw.rectangle([(x1, text_y), (x1 + text_w + 6, text_y + text_h + 4)], fill=(0, 0, 0, 160))
                    draw.text((x1 + 3, text_y + 2), label, font=font, fill=(255, 255, 255, 255))
                    frame = cv2.cvtColor(np.array(pil_frame), cv2.COLOR_RGB2BGR)

            final_writer.write(frame.astype(np.uint8))

        cap.release()
        final_writer.release()

        # 4) 브라우저 호환 MP4로 변환
        ffmpeg_command = [
            "ffmpeg", "-y", "-i", str(final_avi_path),
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(final_video_path)
        ]
        subprocess.run(ffmpeg_command, check=True)

        if not final_video_path.exists() or final_video_path.stat().st_size == 0:
            raise IOError("최종 MP4 파일이 생성되지 않았거나 비어 있음.")

        tasks[task_id] = {"status": "SUCCESS", "result": f"/results/{final_video_path.name}"}
        print(f"[{task_id}] ✅ 최종 비디오 생성 성공.")

        with open(final_video_path, "rb") as f:
            video_bytes = f.read()

        # DB 저장 로직
        ripeness_labels = []
        confidences = []
        # 모델 결과를 다시 열어서 가장 많은 ripeness 추출
        cap = cv2.VideoCapture(str(final_avi_path))
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if model:
                results = model(frame, verbose=False)
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    confidences.append(conf)
                    cls_name = model.names[cls_id]
                    ripeness = KOREAN_CLASSES.get(cls_name, cls_name)
                    ripeness_labels.append(ripeness)
        cap.release()

        # 가장 많은 ripeness 하나 선택
        if ripeness_labels:
            final_ripeness = Counter(ripeness_labels).most_common(1)[0][0]
        else:
            final_ripeness = "분석불가"

        freshness = LABEL_SCORE.get(final_ripeness, 0)
        avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else 0.0

        try:
            username = current_user.nickname if current_user else "unknown"
            db.add(Analysis(
                username=username,
                ripeness=final_ripeness,  # ✅ 실제 가장 흔한 숙성도로 기록
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
        if video_writer is not None:
            video_writer.release()
        if cap is not None:
            cap.release()
        if final_writer is not None:
            final_writer.release()
        if intermediate_video_path.exists():
            intermediate_video_path.unlink()
        if final_avi_path.exists():
            final_avi_path.unlink()
        if tasks.get(task_id, {}).get("status") == "FAILURE" and final_video_path.exists():
            final_video_path.unlink()

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
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        detections = run_yolo_model(image)  # 기존 YOLO 결과

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
    if len(files) < 1: # [수정] 1장 이상이면 비디오 분석 가능하도록 변경
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="동영상 분석을 위해서는 1장 이상의 이미지가 필요합니다."
        )

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "PENDING", "result": None}

    images_for_video = []  # [핵심 수정] 동영상 생성에 사용할 이미지 데이터 리스트
    image_results = []     # [핵심 수정] 프론트로 즉시 반환할 분석 결과 리스트

    for file in files:
        content = await file.read()
        if not content:
            continue
        
        # [핵심 수정] 동영상 생성을 위해 파일 내용을 리스트에 추가합니다.
        images_for_video.append(content)

        # --- 각 이미지에 대한 개별 분석을 즉시 수행 ---
        try:
            pil_image = Image.open(io.BytesIO(content)).convert("RGB")
            
            # run_yolo_model 함수를 재사용하여 분석 로직을 통일합니다.
            detections = run_yolo_model(pil_image)

            # ✅ 평균 계산
            avg_conf = sum(d["confidence"] for d in detections) / len(detections) if detections else 0
            avg_fresh = sum(d["freshness"] for d in detections) / len(detections) if detections else 0

            # ✅ DB에 저장
            db = SessionLocal()
            try:
                db.add(Analysis(
                    username=current_user.nickname,
                    ripeness=detections[0]["ripeness"] if detections else "분석불가",
                    confidence=avg_conf,
                    freshness=avg_fresh,
                    image_blob=content,
                    created_at=datetime.now(KST)
                ))
                db.commit()
            finally:
                db.close()

            # 프론트엔드로 보낼 결과 데이터 구조를 만듭니다.
            image_results.append({
                "filename": file.filename,
                "detections": detections, # run_yolo_model의 결과를 그대로 사용
                "avg_confidence": avg_conf
            })
        except Exception as e:
            # 특정 이미지 분석에 실패하더라도 계속 진행합니다.
            print(f"파일 분석 실패: {file.filename}, 오류: {e}")
            image_results.append({
                "filename": file.filename,
                "detections": [],
                "avg_confidence": 0,
                "error": str(e) # 에러 정보 추가
            })

    # [핵심 수정] 내용이 채워진 images_for_video 리스트를 백그라운드 스레드에 전달합니다.
    if images_for_video:
        thread = threading.Thread(target=create_analysis_video, args=(current_user, task_id, images_for_video))
        thread.start()
    else:
        # 유효한 이미지가 하나도 없는 경우 즉시 실패 처리
        tasks[task_id] = {"status": "FAILURE", "result": "유효한 이미지가 없습니다."}


    # [핵심 수정] 동영상 생성 시작과 동시에, 각 이미지의 분석 결과를 즉시 프론트로 반환합니다.
    return {"task_id": task_id, "results": image_results}

# --- 작업 상태 확인 라우터 (인증 필요 없음) ---
@analysis_router.get("/tasks/{task_id}/status")
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

from datetime import date

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
        yest_stat = db.query(DailyAnalysisStat).filter(DailyAnalysisStat.date == yesterday).first()

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
            "avg_freshness_yesterday": fresh_yest
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


# --- 최종 라우터 등록 ---
app.include_router(auth_router) # @app.post('/login') 등을 여기에 포함시키려면 auth_router로 변경해야 함
app.include_router(analysis_router)
app.include_router(task_router)
app.include_router(stats_router)

# --- ✅ 루트 확인용 ---
@app.get("/")
def root():
    return {"message": "🍌 바나나 YOLO 분석 서버 작동 중"}