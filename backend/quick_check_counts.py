# quick_check_counts.py
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

SQLITE_URL = "sqlite:///C:/Users/602-19/YOLO/yolo_web/backend/users.db"  # 네 실제 경로
PG_URL = os.getenv("DATABASE_URL")  # PowerShell에 이미 넣어두었을 것

s_engine = create_engine(SQLITE_URL)
p_engine = create_engine(PG_URL, pool_pre_ping=True, connect_args={"sslmode":"require"})

tables = ["users", "analysis", "daily_analysis_stat"]

with s_engine.connect() as sc, p_engine.connect() as pc:
    for t in tables:
        s = sc.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
        p = pc.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
        print(f"{t}: sqlite={s}  postgres={p}")