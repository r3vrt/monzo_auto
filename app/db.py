"""
Database setup for the Monzo automation app.
Uses SQLAlchemy ORM with PostgreSQL as the source of truth.
Loads environment variables from a .env file if present.
"""

import os
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Load environment variables from .env file
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://username:password@localhost/monzo_app"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db_session() -> Generator[Session, None, None]:
    """
    Yields a new SQLAlchemy session. Use with context manager for safety.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
