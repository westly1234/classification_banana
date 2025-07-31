# backend/models.py

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import pytz

KST = pytz.timezone("Asia/Seoul")
def get_kst_now():
    return datetime.now(KST)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    nickname = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    is_verified = Column(Integer, default=0)  # 0=미인증, 1=인증됨
    is_superuser = Column(Boolean, default=False)

class Analysis(Base):
    __tablename__ = "analysis"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)            # 사용자 이메일 or "anonymous"
    ripeness = Column(String, index=True)            # ex: "완숙"
    confidence = Column(Float)
    image_path = Column(String, nullable=True)       # ✅ 이미지 경로
    video_path = Column(String, nullable=True)       # ✅ 비디오 경로
    created_at = Column(DateTime, default=get_kst_now)
