from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Analysis, DailyAnalysisStat
from datetime import datetime, timedelta
import pytz
import random

# DB 경로 (여기에 맞게 수정)
DATABASE_URL = "sqlite:///./users.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session = SessionLocal()

# 한국 시간
KST = pytz.timezone("Asia/Seoul")
today = datetime(2025, 8, 4, tzinfo=KST)
dates = [today - timedelta(days=i) for i in range(5)]

for d in dates:
    for _ in range(5):
        session.add(Analysis(
            username="관리자",
            ripeness=random.choice(["썩음", "신선한 미숙", "신선한 완숙"]),
            freshness=round(random.uniform(60, 95), 2),
            confidence=round(random.uniform(70, 100), 2),
            image_path=f"dummy/image_{random.randint(1,100)}.jpg",
            video_path=f"dummy/video_{random.randint(1,100)}.mp4",
            created_at=d
        ))

    session.add(DailyAnalysisStat(
        date=d.date(),
        variety_count=random.randint(1, 3),
        freshness=round(random.uniform(70, 95), 2),
        accuracy=round(random.uniform(80, 99), 2),
        total_count=5
    ))

session.commit()
session.close()
