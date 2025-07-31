# --- 📁 backend/main.py ---

import base64, os, io, uuid, threading, smtplib, pytz, cv2, time, subprocess, numpy as np
from datetime import datetime, timedelta
from pytz import timezone
from pathlib import Path
from markupsafe import Markup
from PIL import Image, ImageFont, ImageDraw
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
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, func
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
from models import User, Analysis

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
SQLALCHEMY_DATABASE_URL = "sqlite:///./users.db"
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
    username = Column(String, index=True)
    ripeness = Column(String)
    confidence = Column(Float)
    image_path = Column(String, nullable=True)
    video_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=get_kst_now)

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

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://192.168.0.48:5173",
]
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

# --- YOLO 분석 함수 (여러 객체 지원) ---
def run_yolo_model(image: Image.Image):
    """
    이미지에서 감지된 모든 바나나 객체의 정보를 리스트로 반환합니다.
    감지된 객체가 없으면 빈 리스트를 반환합니다.
    """
    if not model:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="모델을 사용할 수 없습니다.")

    img_array = np.array(image)
    results = model(img_array, verbose=False)[0]
    
    analysis_results = []
    VALID_CLASSES = {"ripe", "unripe", "freshripe", "freshunripe", "overripe", "rotten"}

    if results.boxes:
        for box in results.boxes:
            cls_name = model.names[int(box.cls.item())]
            
            # ✅ 감지된 객체가 바나나 종류일 경우에만 결과에 추가
            if cls_name in VALID_CLASSES:
                conf = float(box.conf.item())
                x1, y1, x2, y2 = box.xyxy[0]
                
                bbox = {
                    "x": round(x1.item() / image.width, 4),
                    "y": round(y1.item() / image.height, 4),
                    "width": round((x2 - x1).item() / image.width, 4),
                    "height": round((y2 - y1).item() / image.height, 4),
                }
                
                analysis_results.append({
                    "ripeness": KOREAN_CLASSES.get(cls_name, cls_name),
                    "confidence": round(conf, 3),
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

# --- 📹 비동기 작업 및 동영상 생성 ---

COLOR_MAP = {
    "신선한 완숙": (0, 255, 0),      # 초록
    "신선한 미숙": (0, 200, 255),    # 청록
    "과숙": (255, 165, 0),           # 주황
    "완숙": (0, 255, 255),           # 노랑
    "썩음": (255, 0, 0),             # 빨강
    "미숙": (0, 0, 255)              # 파랑
}

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

def create_analysis_video(task_id: str, image_data_list: list):
    """
    여러 이미지를 받아 스크롤링 분석 비디오를 생성하고 모델 결과를 시각화.
    최종 출력은 웹 브라우저에서 재생 가능한 MP4(H.264 + yuv420p)로 저장됨.
    """
    intermediate_video_path = RESULTS_DIR / f"{task_id}_intermediate.avi"
    final_avi_path = RESULTS_DIR / f"{task_id}_final.avi"
    final_video_path = RESULTS_DIR / f"{task_id}_final.mp4"

    video_writer, cap, final_writer = None, None, None

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
@analysis_router.post("/analyze", response_model=list[YoloAnalysisResult])
def analyze_single_image(payload: ImagePayload, current_user: User = Depends(get_current_user)):
    if not model:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="모델이 현재 사용할 수 없습니다.")
    try:
        image_data = base64.b64decode(payload.image)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        result = run_yolo_model(image) # 기존에 만들어둔 분석 함수 호출
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"이미지 분석 중 오류 발생: {e}")

@analysis_router.post("/analyze_video")
async def start_video_analysis(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    if len(files) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="동영상 분석을 위해서는 2장 이상의 이미지가 필요합니다."
        )

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "PENDING", "result": None}

    images = []
    image_results = []
    db = SessionLocal()
    try:
        for file in files:
            content = await file.read()
            if not content:
                print(f"⚠️ {file.filename} is empty")
                continue

            # ✅ 동영상 생성용 저장
            images.append(content)

            # ✅ YOLO 분석
            pil_image = Image.open(io.BytesIO(content)).convert("RGB")
            cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            results = model(cv_image, verbose=False)

            detections = []
            for box in results[0].boxes:
                x1, y1, x2, y2 = [float(i) for i in box.xyxy[0]]
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = KOREAN_CLASSES.get(model.names[cls_id], model.names[cls_id])

                # ✅ DB 저장
                db.add(Analysis(
                    username=current_user.nickname,
                    ripeness=cls_name,
                    confidence=conf,
                    image_path=file.filename,
                    video_path=f"/results/{task_id}_final.mp4"
                ))
            
                detections.append({
                    "label": cls_name,
                    "confidence": conf,
                    "boundingBox": {
                        "x": x1 / cv_image.shape[1],
                        "y": y1 / cv_image.shape[0],
                        "width": (x2 - x1) / cv_image.shape[1],
                        "height": (y2 - y1) / cv_image.shape[0]
                    }
                })

            image_results.append({"filename": file.filename, "detections": detections})
        db.commit()
    finally:
        db.close()

    # ✅ 백그라운드 스레드 실행
    thread = threading.Thread(target=create_analysis_video, args=(task_id, images))
    thread.start()

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
@stats_router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    total = db.query(Analysis).count()
    today = datetime.now(KST).date()
    today_count = db.query(Analysis).filter(Analysis.created_at >= today).count()
    all_records = db.query(Analysis).all()

    if not all_records:
        return {"todayAnalyses": 0, "avgRipeness": 0.0, "totalUploads": 0}

    label_score = {"미숙": 1, "신선한 미숙": 2, "완숙": 3, "신선한 완숙": 4, "과숙": 5, "썩음": 6}
    avg_score = sum([label_score.get(a.ripeness, 0) for a in all_records]) / len(all_records)

    return {"todayAnalyses": today_count, "avgRipeness": round(avg_score, 2), "totalUploads": total}

@stats_router.get("/stats/summary")
def get_summary_stats():
    db = SessionLocal()
    try:
        today_date = datetime.now(timezone("Asia/Seoul")).date()
        yesterday_date = today_date - timedelta(days=1)

        total_count = db.query(func.count(Analysis.id)).scalar()

        today_count = db.query(func.count(Analysis.id)).filter(
            func.date(Analysis.created_at) == today_date
        ).scalar()

        yesterday_count = db.query(func.count(Analysis.id)).filter(
            func.date(Analysis.created_at) == yesterday_date
        ).scalar()

        total_before_today = db.query(func.count(Analysis.id)).filter(
            func.date(Analysis.created_at) < today_date
        ).scalar()

        ripeness_counts_query = (
            db.query(Analysis.ripeness, func.count(Analysis.id))
            .group_by(Analysis.ripeness)
            .all()
        )
        ripeness_counts = {ripeness: count for ripeness, count in ripeness_counts_query}

        ripeness_types_yesterday = (
            db.query(Analysis.ripeness)
            .filter(func.date(Analysis.created_at) <= yesterday_date)
            .distinct()
            .count()
        )

        avg_confidence_today = db.query(func.avg(Analysis.confidence)).filter(
            func.date(Analysis.created_at) == today_date
        ).scalar() or 0

        avg_confidence_yesterday = db.query(func.avg(Analysis.confidence)).filter(
            func.date(Analysis.created_at) == yesterday_date
        ).scalar() or 0

        return {
            "today": today_count,
            "yesterday": yesterday_count,
            "total": total_count,
            "total_before_today": total_before_today,
            "ripeness_counts": ripeness_counts,
            "ripeness_types_yesterday": ripeness_types_yesterday,
            "avg_confidence_today": round(avg_confidence_today * 100, 2),
            "avg_confidence_yesterday": round(avg_confidence_yesterday * 100, 2)
        }
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