import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# 데이터베이스 URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://kbo_user:kbo_password@localhost:5432/kbo_dashboard"
)

# SQLAlchemy 엔진 생성 (DB_ECHO=true 일 때만 SQL 로깅)
DB_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"
engine = create_engine(DATABASE_URL, echo=DB_ECHO)

# 세션팩토리 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 베이스 클래스
Base = declarative_base()


def get_db():
    """데이터베이스 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """데이터베이스 테이블 생성"""
    Base.metadata.create_all(bind=engine)
