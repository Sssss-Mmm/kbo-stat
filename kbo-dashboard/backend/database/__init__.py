import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# 테스트 실행 중(unittest·pytest 가 먼저 로드됨)에는 .env·DATABASE_URL·기본 localhost 를 쓰지 않는다 — 운영 DB 나 이 PC 의
# 다른 프로젝트 DB 에 닿지 않게(main 은 import 때 init_db 로 테이블을 만든다). 대상은 TEST_DATABASE_URL 로만 명시, 없으면 메모리 SQLite.
# 운영 실행(uvicorn main:app)은 둘 다 로드하지 않아 아래 기존 경로 그대로다.
TESTING = "unittest" in sys.modules or "pytest" in sys.modules

if TESTING:
    DATABASE_URL = os.getenv("TEST_DATABASE_URL") or "sqlite://"
else:
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
