from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import exc
from contextlib import contextmanager
from typing import Generator, Optional

SQLALCHEMY_DATABASE_URL = "sqlite:///./backend/shopflow.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    """
    Initialize database: create all tables.
    Safe to call multiple times.
    """
    Base.metadata.create_all(bind=engine)

def get_db() -> Generator[sessionmaker, None, None]:
    """
    Dependency to provide DB session.
    Yields a new session per request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def health_check() -> bool:
    """
    Basic DB health check: execute simple query.
    Returns True if DB responds, False otherwise.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (exc.OperationalError, exc.DBAPIError):
        return False