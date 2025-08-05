# backend/db.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
import os

# 절대 경로로 users.db 지정
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")  # backend/users.db
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})

SessionLocal = sessionmaker(bind=engine)

# 테이블 생성
def init_db():
    Base.metadata.create_all(bind=engine)
