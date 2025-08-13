# fix_sequences.py
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

PG_URL = os.getenv("DATABASE_URL")  # 이미 세션에 설정돼 있다면 그대로 사용

engine = create_engine(PG_URL, pool_pre_ping=True, connect_args={"sslmode":"require"})
with engine.begin() as c:
    for t in ["users","analysis","daily_analysis_stat"]:
        try:
            c.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}','id'), COALESCE((SELECT MAX(id) FROM {t}),0)+1, false);"))
            print(f"sequence fixed: {t}")
        except Exception as e:
            print(f"skip {t}: {e}")
