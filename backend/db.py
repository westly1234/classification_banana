# db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
# Render PG는 보통 SSL 필요
if DATABASE_URL and "render.com" in DATABASE_URL:
    connect_args["sslmode"] = "require"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# 모든 ORM 모델이 상속할 베이스
Base = declarative_base()

def init_db():
    # 모델들을 등록하기 위해 지연 import (순환 방지)
    import models  # noqa: F401
    # Alembic을 쓰면 create_all은 보통 생략합니다.
    # Base.metadata.create_all(bind=engine)
