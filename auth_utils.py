# backend/auth_utils.py
from datetime import datetime, timedelta
from typing import Any, Dict
import hashlib
import bcrypt

import os
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import SessionLocal
from . import models

# ===== JWT 기본 설정 =====
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change_me_secret_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24시간


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    입력한 비밀번호가 저장된 해시와 같은지 검사
    """
    # SHA256으로 먼저 해시
    plain_hashed = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    # bcrypt로 검증
    return bcrypt.checkpw(plain_hashed.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """
    비밀번호를 bcrypt 해시로 변환
    """
    # SHA256으로 먼저 해시 (72바이트 제한 해결)
    password_hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()
    # bcrypt로 해시
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_hashed.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(data: Dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    JWT 액세스 토큰 생성
    - data: {"sub": email} 이런 형태로 사용
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ===== DB 세션 의존성 =====
from .database import SessionLocal  # 프로젝트에 맞게 수정

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===== OAuth2 설정 =====
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    """
    JWT 토큰에서 현재 사용자 정보 추출
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보를 확인할 수 없습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    
    return user  # type: ignore[return-value]


async def get_current_admin(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    """
    관리자 권한 확인
    """
    if str(current_user.role) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다."
        )
    return current_user
