# wipe_pg_tables.py
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# 1) DATABASE_URL을 .env 또는 환경변수로 읽기
PG_URL = os.getenv("DATABASE_URL")

# 2) 환경변수에 없다면 직접 문자열 넣어도 됩니다. (필요시 아래 한 줄 주석 해제 후 본인 URL로 수정)
# PG_URL = "postgresql+psycopg2://banana_database_user:비밀번호@dpg-....singapore-postgres.render.com:5432/banana_database?sslmode=require"

if not PG_URL:
    raise SystemExit("DATABASE_URL이 없습니다. 환경변수로 지정하거나 스크립트 내 PG_URL을 채워주세요.")

# 3) 엔진 생성 (ssl 강제)
engine = create_engine(PG_URL, pool_pre_ping=True, connect_args={"sslmode": "require"})

with engine.begin() as conn:
    conn.execute(text("TRUNCATE TABLE analysis, daily_analysis_stat, users RESTART IDENTITY CASCADE;"))
    for t in ["users", "analysis", "daily_analysis_stat"]:
        cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t};")).scalar()
        print(f"{t}: {cnt}")
        
print("TRUNCATE 완료")
