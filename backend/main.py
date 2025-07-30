# --- 📁 backend/main.py ---

import base64
import io
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import Column, Integer, String, DateTime, create_engine, func, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from pydantic import BaseModel
from PIL import Image
import numpy as np
from ultralytics import YOLO
from db import SessionLocal, init_db
from models import Analysis
import pytz, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jose import jwt, JWTError

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
    "http://localhost:5173",  # Vite/React 개발 서버
    "http://127.0.0.1:5173",
    "http://192.168.0.48:5173", # 실제 사용중인 로컬 IP
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
# --- DB 세션 종속성 ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- YOLO 로드 ---
model = YOLO("yolov8s.pt")

KOREAN_CLASSES = {
    "freshripe": "신선한 완숙",
    "freshunripe": "신선한 미숙",
    "overripe": "과숙",
    "ripe": "완숙",
    "rotten": "썩음",
    "unripe": "미숙"
}

# --- 분석 함수 ---
def run_yolo_model(image: Image.Image):
    img_array = np.array(image)
    results = model(img_array)[0]
    if not results.boxes:
        raise ValueError("감지된 바운딩 박스가 없습니다.")

    best_idx = results.boxes.conf.argmax().item()
    box = results.boxes[best_idx]
    cls_id = int(box.cls.item())
    cls_name = model.names[cls_id]
    ko_cls_name = KOREAN_CLASSES.get(cls_name, cls_name)
    conf = float(box.conf.item())

    x1, y1, x2, y2 = box.xyxy[0]
    img_w, img_h = image.size
    bbox = {
        "x": round(x1.item() / img_w, 3),
        "y": round(y1.item() / img_h, 3),
        "width": round((x2.item() - x1.item()) / img_w, 3),
        "height": round((y2.item() - y1.item()) / img_h, 3),
    }
    result = {
        "ripeness": ko_cls_name,
        "confidence": round(conf, 3),
        "boundingBox": bbox
    }
    # 결과 DB에 저장
    db = SessionLocal()
    db_result = Analysis(ripeness=ko_cls_name, confidence=conf)
    db.add(db_result)
    db.commit()
    db.close()

    return result

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

# --- 🔍 이미지 분석 후 DB 저장 ---
@app.post("/analyze")
def analyze(payload: ImagePayload, db: Session = Depends(get_db)):
    try:
        image_data = base64.b64decode(payload.image)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        result = run_yolo_model(image)

        db.add(Analysis(
            username="anonymous",
            ripeness=result['ripeness'],
            confidence=result['confidence']
        ))
        db.commit()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 📊 통계 API ---
@app.get("/stats", response_model=StatsResponse)
def stats(db: Session = Depends(get_db)):
    total = db.query(Analysis).count()
    today = datetime.now(KST).date()
    today_count = db.query(Analysis).filter(Analysis.created_at >= today).count()
    all_records = db.query(Analysis).all()

    if not all_records:
        return {"todayAnalyses": 0, "avgRipeness": 0.0, "totalUploads": 0}

    label_score = {"미숙": 1, "신선한 미숙": 2, "완숙": 3, "신선한 완숙": 4, "과숙": 5, "썩음": 6}
    avg_score = sum([label_score.get(a.ripeness, 0) for a in all_records]) / len(all_records)

    return {
        "todayAnalyses": today_count,
        "avgRipeness": round(avg_score, 2),
        "totalUploads": total
    }

router = APIRouter()

@router.get("/stats/summary")
def get_summary():
    db = SessionLocal()
    today_str = datetime.now(KST).strftime("%Y-%m-%d")

    total = db.query(func.count(Analysis.id)).scalar()

    today = db.query(func.count(Analysis.id))\
        .filter(func.date(Analysis.created_at) == today_str)\
        .scalar()

    ripeness_counts = db.query(Analysis.ripeness, func.count())\
        .group_by(Analysis.ripeness)\
        .all()
    
    db.close()

    return {
        "total": total,
        "today": today,
        "ripeness_counts": {r: c for r, c in ripeness_counts}
    }

app.include_router(router) 

# --- ✅ 루트 확인용 ---
@app.get("/")
def root():
    return {"message": "🍌 바나나 YOLO 분석 서버 작동 중"}
