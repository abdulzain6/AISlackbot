from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import create_engine
from typing import Generator
import os, dotenv


dotenv.load_dotenv()

# Database connection setup for PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")

# Create the SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,        # Ensures the connection is alive before using
    pool_size=20,              # Sets the connection pool size
    max_overflow=10,           # Allows for overflow connections
    echo=False,                # Set to True for SQL debugging
    future=True                # Enables SQLAlchemy 2.0 style usage
)

# Scoped session for thread-safe database operations
SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
)

# Base declarative class for model creation
Base = declarative_base()

# Dependency to ensure a database session is available
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()