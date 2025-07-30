# --- 📁 backend/main.py ---

# --- 📁 backend/main.py ---

# 기존 import 문들을 아래 내용으로 완전히 교체하세요.

import base64, io, uuid, threading, smtplib, pytz, cv2, time, numpy as np
from datetime import datetime
from pathlib import Path
from PIL import Image
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# FastAPI 및 관련 라이브러리
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Request, status, Header
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

# 인증 관련 라이브러리
from jose import jwt, JWTError
from passlib.context import CryptContext

# SQLAlchemy 관련 import 문 추가
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, func
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
    confidence = Column(String)
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
    name = "Analysis"
    name_plural = "Analysis" 
    column_list = [Analysis.id, Analysis.username, Analysis.ripeness, Analysis.created_at]

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
# main.py 파일에서 이 함수를 찾아서 아래 내용으로 덮어쓰세요.
import time # time 라이브러리가 import 되어 있는지 확인해주세요.

def create_analysis_video(task_id: str, image_data_list: list):
    """
    여러 이미지를 받아 스크롤링 분석 비디오를 만드는 백그라운드 작업 함수.
    [최종 수정] Pillow를 이용한 매우 안정적인 이미지 처리 파이프라인 적용.
    """
    try:
        tasks[task_id] = {"status": "PROCESSING", "result": None}
        print(f"[{task_id}] 비디오 생성 시작...")
        
        output_width, output_height, fps = 640, 480, 15
        
        resized_imgs = [cv2.resize(img, (output_width, output_height)) for img in resized_imgs if img is not None]
        for index, b64_data in enumerate(image_data_list):
            try:
                img_data = base64.b64decode(b64_data)
                
                # 1단계: Pillow로 이미지를 열고 RGB로 표준화
                pil_image = Image.open(io.BytesIO(img_data)).convert("RGB")
                
                # 2단계: Pillow 이미지를 NumPy 배열로 변환
                # PIL(RGB) -> OpenCV(BGR) 색상 순서 변환
                cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                
                resized_imgs.append(cv2.resize(cv_image, (output_width, output_height)))
            except Exception as img_err:
                # 특정 이미지 처리 실패 시 로그를 남기고 건너뜀
                print(f"[{task_id}] 경고: {index+1}번째 이미지 처리 실패. 건너뜁니다. 오류: {img_err}")
                continue

        if not resized_imgs:
            raise ValueError("유효한 이미지가 없습니다.")
        print(f"[{task_id}] {len(resized_imgs)}개 이미지 리사이즈 및 표준화 완료.")

        long_img = np.hstack(resized_imgs)
        if long_img.shape[1] <= output_width:
            raise ValueError("비디오를 만들기에 이미지가 충분하지 않습니다.")

        temp_video_path = RESULTS_DIR / f"{task_id}_temp.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(str(temp_video_path), fourcc, fps, (output_width, output_height))
        
        total_frames = fps * 10
        for i in range(total_frames):
            start_x = int((long_img.shape[1] - output_width) * (i / (total_frames - 1)))
            end_x = start_x + output_width
            if end_x > long_img.shape[1]:
                end_x = long_img.shape[1]
                start_x = end_x - output_width
            frame = long_img[:, start_x:end_x]
            video_writer.write(frame)
        video_writer.release()
        print(f"[{task_id}] 임시 비디오 생성 완료: {temp_video_path}")
        time.sleep(0.5)

        cap = cv2.VideoCapture(str(temp_video_path))
        if not cap.isOpened():
             raise IOError(f"생성된 임시 비디오 파일({temp_video_path})을 열 수 없습니다.")
        
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"[{task_id}] 임시 비디오에서 {frame_count}개 프레임 읽기 시작...")
        final_video_path = RESULTS_DIR / f"{task_id}_final.mp4"
        final_writer = cv2.VideoWriter(str(final_video_path), fourcc, fps, (output_width, output_height))
        
        processed_frames = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            if model:
                results = model(frame, verbose=False)
                final_writer.write(results[0].plot())
            else:
                final_writer.write(frame)
            processed_frames += 1
        
        print(f"[{task_id}] {processed_frames}/{frame_count}개 프레임 처리 완료.")
        cap.release()
        final_writer.release()
        temp_video_path.unlink()

        tasks[task_id] = {"status": "SUCCESS", "result": f"/results/{final_video_path.name}"}
        print(f"[{task_id}] ✅ 최종 비디오 생성 성공: {final_video_path.name}")

    except Exception as e:
        tasks[task_id] = {"status": "FAILURE", "result": str(e)}
        print(f"[{task_id}] ❌ 비디오 생성 실패: {e}")

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
async def start_video_analysis(request: Request, current_user: User = Depends(get_current_user)):
    data = await request.json()
    images = data.get("images", [])
    if len(images) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="동영상 분석을 위해서는 2장 이상의 이미지가 필요합니다.")
    
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "PENDING", "result": None}
    
    thread = threading.Thread(target=create_analysis_video, args=(task_id, images))
    thread.start()
    
    return {"task_id": task_id}

# --- 작업 상태 확인 라우터 (인증 필요 없음) ---
@task_router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="작업을 찾을 수 없습니다.")
    return task

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
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    total = db.query(func.count(Analysis.id)).scalar()
    today = db.query(func.count(Analysis.id)).filter(func.date(Analysis.created_at) == today_str).scalar()
    ripeness_counts = db.query(Analysis.ripeness, func.count()).group_by(Analysis.ripeness).all()
    db.close()
    return {"total": total, "today": today, "ripeness_counts": {r: c for r, c in ripeness_counts}}

# --- 최종 라우터 등록 ---
app.include_router(auth_router) # @app.post('/login') 등을 여기에 포함시키려면 auth_router로 변경해야 함
app.include_router(analysis_router)
app.include_router(task_router)
app.include_router(stats_router)

# --- ✅ 루트 확인용 ---
@app.get("/")
def root():
    return {"message": "🍌 바나나 YOLO 분석 서버 작동 중"}