# backend/database.py

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# backend/.env 파일을 명시적으로 로드
backend_dir = Path(__file__).parent
env_path = backend_dir / ".env"
load_dotenv(dotenv_path=env_path)

# 1) 환경변수에서 DATABASE_URL 먼저 찾고,
# 2) 없으면 자동으로 SQLite 파일 사용
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # 프로젝트 루트 기준 dreamwish_cs.db 라는 SQLite 파일 생성
    DATABASE_URL = "sqlite:///./dreamwish_cs.db"

# SQLite면 check_same_thread 옵션 필요
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,  # SQL 로그 보고 싶으면 True
    )
else:
    # 나중에 진짜 Postgres 쓰고 싶을 때는 여기로 연결됨
    engine = create_engine(DATABASE_URL, echo=False)

# 세션팩토리
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base 모델
Base = declarative_base()
