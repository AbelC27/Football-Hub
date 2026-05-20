from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/football_analytics")

# Supabase free-tier session pooler caps total clients at 15 across the whole
# project. A FastAPI process plus autoreload, scheduler, and WebSocket can
# easily blow that. We keep the per-process pool small (5 + 5 overflow = 10
# max) so two concurrent processes during a reload still fit under the cap.
# Override via env vars if needed for local Postgres or paid tiers.
_pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "5"))
_pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "10"))

# `connect_timeout` (psycopg2) caps the time spent on each TCP attempt, so a
# dead IP behind a pooled hostname fails fast instead of hanging ~75s.
# `pool_pre_ping` issues a cheap SELECT 1 before handing out a connection so
# stale sockets (frequent with poolers) get recycled transparently.
# `pool_recycle` proactively replaces connections older than 30 minutes,
# matching Supabase's idle-timeout window.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_timeout=_pool_timeout,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
