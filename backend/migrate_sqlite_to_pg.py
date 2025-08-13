import os, time, gc
from pathlib import Path
from sqlalchemy import create_engine, inspect, Table, MetaData, select, update, text, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import insert
from dotenv import load_dotenv

load_dotenv()

# --- 경로/URL ---
SQLITE_FILE = Path(__file__).resolve().parent / "users.db"   # ← 실제 파일명
SQLITE_URL  = os.getenv("SQLITE_URL", f"sqlite:///{SQLITE_FILE.as_posix()}")
PG_URL      = os.getenv("DATABASE_URL")
if not PG_URL:
    raise SystemExit("DATABASE_URL 환경변수가 없습니다. External URL + '?sslmode=require' 로 설정하세요.")

# --- 엔진: keepalive/ssl ---
src_engine = create_engine(SQLITE_URL)
dst_engine = create_engine(
    PG_URL,
    pool_pre_ping=True,
    connect_args={
        "sslmode": "require",
        "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 5,
    },
)
SrcSession = sessionmaker(bind=src_engine)

print(f"🔎 SQLITE_URL = {SQLITE_URL}")
if SQLITE_URL.startswith("sqlite:///"):
    p = SQLITE_URL.replace("sqlite:///", "")
    print(f"   └ 파일 존재? {Path(p).exists()}  size={Path(p).stat().st_size if Path(p).exists() else 'N/A'} bytes")
print(f"DATABASE_URL = {PG_URL.split('@')[0]}@... (masked)")

src_ins = inspect(src_engine)
dst_ins = inspect(dst_engine)
src_tables = set(src_ins.get_table_names())
dst_tables = set(dst_ins.get_table_names())
print(f"SQLite 테이블: {sorted(list(src_tables))}")
print(f"Postgres 테이블: {sorted(list(dst_tables))}")

TARGETS_SIMPLE = ["users", "daily_analysis_stat"]  # BLOB 없는 테이블들
TARGET_ANALYSIS = "analysis"                       # BLOB 있는 테이블

def pg_upsert_batch(dst_t, pk_cols):
    """ON CONFLICT DO NOTHING로 중복 건너뜀"""
    stmt = insert(dst_t)  # ← 여기서는 values() 절대 넣지 않음
    if pk_cols:
        stmt = stmt.on_conflict_do_nothing(index_elements=pk_cols)
    return stmt

def copy_simple_table(tname: str, batch_size: int = 500):
    if tname not in src_tables:
        print(f"SQLite에 '{tname}' 없음 → 건너뜀"); return
    if tname not in dst_tables:
        print(f"Postgres에 '{tname}' 없음 → (alembic upgrade head 먼저)"); return

    src_md = MetaData(); dst_md = MetaData()
    src_t = Table(tname, src_md, autoload_with=src_engine)
    dst_t = Table(tname, dst_md, autoload_with=dst_engine)

    common_cols = [c.name for c in src_t.columns if c.name in dst_t.c]
    insp = inspect(dst_engine)
    pk_cols = insp.get_pk_constraint(tname).get("constrained_columns") or (["id"] if "id" in common_cols else [])

    # 총 개수
    total = None
    try:
        with src_engine.connect() as c:
            total = c.execute(text(f'SELECT COUNT(*) FROM "{tname}"')).scalar()
    except Exception:
        pass

    # id로 정렬 가능하면 안정적으로 순회
    order_by_id = src_t.c.get("id", None)

    offset = 0; moved = 0
    while True:
        with src_engine.connect() as sconn:
            q = src_t.select().with_only_columns(*[src_t.c[c] for c in common_cols]).offset(offset).limit(batch_size)
            if order_by_id is not None:
                q = q.order_by(order_by_id)
            rows = sconn.execute(q).mappings().all()
        if not rows:
            break

        data = [dict(r) for r in rows] 
        for attempt in range(1, 4):
            try:
                with dst_engine.begin() as dconn:
                    stmt = pg_upsert_batch(dst_t, pk_cols)
                    dconn.execute(stmt, data)   # ← values(data) 아님! 두 번째 인자로 리스트 전달
                moved += len(rows)
                print(f"{tname}: 진행 {moved}/{total if total is not None else '?'}")
                break
            except OperationalError as e:
                wait = min(2 ** attempt, 8)
                print(f"{tname} 배치 업서트 실패 → 재시도 {attempt}/3 (대기 {wait}s): {e}")
                time.sleep(wait)
                if attempt == 3:
                    raise

        offset += len(rows)
        rows = None; gc.collect(); time.sleep(0.02)

def copy_analysis_metadata_then_blobs(meta_batch: int = 300, blob_sleep: float = 0.02):
    tname = TARGET_ANALYSIS
    if tname not in src_tables:
        print(f"SQLite에 '{tname}' 없음 → 건너뜀"); return
    if tname not in dst_tables:
        print(f"Postgres에 '{tname}' 없음 → (alembic upgrade head 먼저)"); return

    src_md = MetaData(); dst_md = MetaData()
    src_t = Table(tname, src_md, autoload_with=src_engine)
    dst_t = Table(tname, dst_md, autoload_with=dst_engine)

    cols = [c.name for c in src_t.columns if c.name in dst_t.c]
    blob_cols = [c for c in ["image_blob","video_blob"] if c in cols]
    meta_cols = [c for c in cols if c not in blob_cols]

    insp = inspect(dst_engine)
    pk_cols = insp.get_pk_constraint(tname).get("constrained_columns") or (["id"] if "id" in cols else [])

    # 총 개수
    with src_engine.connect() as c:
        total = c.execute(text(f'SELECT COUNT(*) FROM "{tname}"')).scalar()
    print(f"{tname}: 총 {total} rows | 메타컬럼 {meta_cols} | BLOB {blob_cols}")

    # 1) 메타데이터만 대량 업서트
    offset = 0; moved_meta = 0
    order_by_id = src_t.c.get("id", None)
    while True:
        with src_engine.connect() as sconn:
            q = src_t.select().with_only_columns(*[src_t.c[c] for c in meta_cols]).offset(offset).limit(meta_batch)
            if order_by_id is not None:
                q = q.order_by(order_by_id)
            rows = sconn.execute(q).mappings().all()
        if not rows:
            break

        data = [dict(r) for r in rows]

        for attempt in range(1, 4):
            try:
                with dst_engine.begin() as dconn:
                    stmt = pg_upsert_batch(dst_t, pk_cols)
                    dconn.execute(stmt, data)   # ← 동일
                moved_meta += len(rows)
                print(f"   · 메타 진행 {moved_meta}/{total}")
                break
            except OperationalError as e:
                wait = min(2 ** attempt, 8)
                print(f" 메타 업서트 재시도 {attempt}/3 (대기 {wait}s): {e}")
                time.sleep(wait)
                if attempt == 3:
                    raise

        offset += len(rows)
        rows = None; gc.collect(); time.sleep(0.02)

    # 2) BLOB은 한 줄씩(또는 아주 작은 배치) UPDATE
    if not blob_cols:
        print("   · BLOB 컬럼 없음 → 스킵")
        return

    print("   · BLOB 업데이트 시작(행 단위)")
    updated = 0
    with src_engine.connect() as sconn:
        # id, blob들만 가져와서 순회
        cols_to_get = [src_t.c["id"]] + [src_t.c[c] for c in blob_cols]
        q = select(*cols_to_get)
        if order_by_id is not None:
            q = q.order_by(order_by_id)
        cursor = sconn.execute(q)
        for row in cursor:
            rid = row._mapping["id"]
            values = {c: row._mapping[c] for c in blob_cols}
            if all(v is None for v in values.values()):
                continue  # BLOB 둘 다 없으면 스킵

            # 행 단위 UPDATE + 재시도
            for attempt in range(1, 5):
                try:
                    with dst_engine.begin() as dconn:
                        stmt = (
                            update(dst_t)
                            .where(dst_t.c.id == rid)
                            .values(**values)
                        )
                        dconn.execute(stmt)
                    updated += 1
                    if updated % 25 == 0:
                        print(f"   · BLOB 진행 {updated}/{total}")
                    break
                except OperationalError as e:
                    wait = min(2 ** attempt, 10)
                    print(f"BLOB 업데이트 실패(id={rid}) → 재시도 {attempt}/4 (대기 {wait}s): {e}")
                    time.sleep(wait)
                    if attempt == 4:
                        raise
            time.sleep(blob_sleep)  # 서버에 살짝 숨 돌릴 시간

    print(f"{tname}: 메타 {moved_meta}건 + BLOB {updated}건 업데이트 완료.")

# ---- 실행 플로우 ----
for t in TARGETS_SIMPLE:
    copy_simple_table(tname=t, batch_size=500)

copy_analysis_metadata_then_blobs(meta_batch=300, blob_sleep=0.02)

print("🎉 DONE")