"""
Database Connection & Session Management for PostgreSQL.
Schema matches Section 4 of the specification.
"""

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

backend_env = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(backend_env):
    load_dotenv(backend_env)
else:
    load_dotenv()

logger = logging.getLogger("predictive_maintenance.db")

# Default PostgreSQL database URL
DEFAULT_DB_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/predictive_maintenance"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

# If DATABASE_URL starts with postgresql:// and not postgresql+psycopg://, adapt for psycopg3
if DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

Base = declarative_base()

db_available = False
engine = None
SessionLocal = None

try:
    # Attempt connecting to PostgreSQL with short timeout to prevent startup hangs if DB is offline
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 2} if "psycopg" in DATABASE_URL else {}
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with engine.connect() as conn:
        db_available = True
        logger.info(f"Connected to PostgreSQL at {DATABASE_URL}")
except Exception as e:
    logger.warning(f"PostgreSQL connection at {DATABASE_URL} failed: {e}")
    logger.warning("Running with dev_fallback.db for local prototyping/testing.")
    fallback_db_path = os.path.join(os.path.dirname(__file__), "..", "dev_fallback.db")
    engine = create_engine(f"sqlite:///{fallback_db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_available = False


def init_db():
    """
    Creates tables if they don't already exist.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")


def get_db():
    """
    FastAPI dependency yielding a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
