# backend/models.py

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, LargeBinary, Date, Text
from sqlalchemy.sql import func
from db import Base 
from datetime import datetime
import pytz

KST = pytz.timezone("Asia/Seoul")
def get_kst_now():
    return datetime.now(KST)

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
    username = Column(String)
    ripeness = Column(String)
    freshness = Column(Float, nullable=True)
    confidence = Column(Float)
    image_path = Column(String, nullable=True)
    video_path = Column(String, nullable=True)
    image_blob = Column(LargeBinary, nullable=True)
    video_blob = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DailyAnalysisStat(Base):
    __tablename__ = "daily_analysis_stat"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True)  # 날짜
    variety_count = Column(Integer, default=0)         # 다양성 (종류 수)
    freshness = Column(Float, default=0.0)              # 신선도(%)
    accuracy = Column(Float, default=0.0)               # 정확도(%)
    total_count = Column(Integer, default=0)            # 총 분석 수

class TaskStatus(Base):
    __tablename__ = "task_status"
    id = Column(String, primary_key=True)             # task_id
    status = Column(String, nullable=False, index=True)   # PENDING / PROCESSING / SUCCESS / FAILURE
    result = Column(String, nullable=True)            # "/results/xxx.mp4" 또는 절대 URL
    image_results = Column(Text, nullable=False, default="[]")  # JSON 문자열(썸네일 결과)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class DailyBoxCount(Base):
    __tablename__ = "daily_box_count"
    date = Column(Date, primary_key=True, index=True)
    counts_json = Column(Text, default="{}")  # {"완숙": 12, "미숙": 3, ...}
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
