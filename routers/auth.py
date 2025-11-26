# backend/routers/auth.py
from typing import cast, Optional
import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .. import models
from ..auth_utils import (
    get_db,
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    get_current_admin,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    role: str
    user_id: int     # 👈 상담원 식별자 (DB PK)


class LoginRequest(BaseModel):
    email: str
    password: str


# ========= 로그인 (JSON) =========
@router.post("/login-json", response_model=TokenResponse)
async def login_json(
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    - 이메일 + 비밀번호로 로그인 (JSON 형식)
    - 해당 이메일 유저가 없으면 '팀원(상담원)'으로 자동 생성 (role='agent')
    """
    email = body.email
    password = body.password

    user = db.query(models.User).filter(models.User.email == email).first()

    # 1) 유저가 없으면: 새 상담원(팀원) 계정 생성 (role='agent')
    if user is None:
        hashed_pw = get_password_hash(password)
        user = models.User(  # type: ignore[reportArgumentType]
            email=email,
            name=email.split("@")[0],
            password_hash=hashed_pw,
            role="agent",  # 기본 상담원
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # 2) 유저가 있는데 비밀번호가 틀린 경우
        stored_hash = cast(str, user.password_hash)
        if not verify_password(password, stored_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            )

    user = cast(models.User, user)

    # 3) 토큰 발급: sub 에 user.id 사용 (상담원 식별자)
    access_token = create_access_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        email=str(user.email),
        role=str(user.role),
        user_id=int(user.id),   # type: ignore[arg-type]
    )


# ========= 로그인 (Form Data) =========
@router.post("/login", response_model=TokenResponse)
async def login(
    username: str = Form(..., description="이메일 주소"),
    password: str = Form(..., description="비밀번호"),
    db: Session = Depends(get_db),
):
    """
    - 이메일 + 비밀번호로 로그인 (Form Data 방식)
    - 해당 이메일 유저가 없으면 '팀원(상담원)'으로 자동 생성 (role='agent')
    """
    email = username
    
    user = db.query(models.User).filter(models.User.email == email).first()

    # 1) 유저가 없으면: 새 상담원(팀원) 계정 생성 (role='agent')
    if user is None:
        hashed_pw = get_password_hash(password)
        user = models.User(  # type: ignore[reportArgumentType]
            email=email,
            name=email.split("@")[0],
            password_hash=hashed_pw,
            role="agent",  # 기본 상담원
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # 2) 유저가 있는데 비밀번호가 틀린 경우
        stored_hash = cast(str, user.password_hash)
        if not verify_password(password, stored_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            )

    user = cast(models.User, user)

    # 3) 토큰 발급: sub 에 user.id 사용 (상담원 식별자)
    access_token = create_access_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        email=str(user.email),
        role=str(user.role),
        user_id=int(user.id),   # type: ignore[arg-type]
    )


# ========= 최초 관리자 생성용 =========
class AdminCreateRequest(BaseModel):
    email: str
    password: str
    admin_secret: str


@router.post("/create-admin", response_model=TokenResponse)
async def create_admin(
    body: AdminCreateRequest,
    db: Session = Depends(get_db),
):
    """
    최초 관리자 생성용 엔드포인트.
    - body.admin_secret 이 .env의 ADMIN_SECRET 과 같아야 함
    - 관리자 role='admin' 으로 생성
    """
    ADMIN_SECRET = os.getenv("ADMIN_SECRET", "change_admin_secret")

    # 1) 관리자 시크릿 검증
    if body.admin_secret != ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 생성 키가 올바르지 않습니다.",
        )

    # 2) 중복 이메일 체크
    existing = db.query(models.User).filter(models.User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 존재하는 이메일입니다.",
        )

    # 3) 관리자 계정 생성 (role='admin')
    hashed_pw = get_password_hash(body.password)
    user = models.User(  # type: ignore[reportArgumentType]
        email=body.email,
        name=body.email.split("@")[0],
        password_hash=hashed_pw,
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    user = cast(models.User, user)

    # sub 에 user.id 사용
    token = create_access_token({"sub": str(user.id)})

    return TokenResponse(
        access_token=token,
        email=str(user.email),
        role=str(user.role),
        user_id=int(user.id),  # type: ignore[arg-type]
    )


# ========= 현재 로그인한 사용자 정보 조회 =========
@router.get("/me", response_model=TokenResponse)
async def get_me(current_user: models.User = Depends(get_current_user)):
    """
    현재 로그인한 사용자 정보 반환
    """
    # 새 토큰 생성 (기존 토큰은 이미 검증됨)
    access_token = create_access_token(data={"sub": str(current_user.id)})
    
    return TokenResponse(
        access_token=access_token,
        email=str(current_user.email),
        role=str(current_user.role),
        user_id=int(current_user.id),  # type: ignore[arg-type]
    )


# ========= 팀원 초대 (관리자 전용) =========
class InviteRequest(BaseModel):
    email: str
    expires_in_hours: int = 168  # 기본 7일 (168시간)


class InviteResponse(BaseModel):
    success: bool
    invite_code: str
    invite_url: str
    email: str
    expires_at: str


@router.post("/invite", response_model=InviteResponse)
async def create_invite(
    body: InviteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    """
    관리자가 팀원 초대 링크 생성
    - role='admin'인 사용자만 호출 가능
    - 초대 코드는 랜덤 생성 (32자)
    - 만료 시간은 기본 7일 (커스터마이징 가능)
    """
    # 이미 가입된 이메일인지 체크
    existing_user = db.query(models.User).filter(models.User.email == body.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 가입된 이메일입니다."
        )
    
    # 기존 초대가 있고 사용되지 않았다면 재사용
    existing_invite = db.query(models.Invite).filter(
        models.Invite.email == body.email,
        models.Invite.used == False
    ).first()
    
    if existing_invite:
        # 기존 초대 연장
        existing_invite.expires_at = datetime.utcnow() + timedelta(hours=body.expires_in_hours)  # type: ignore[attr-defined]
        db.commit()
        db.refresh(existing_invite)
        
        invite_code = str(existing_invite.invite_code)  # type: ignore[attr-defined]
        expires_at = existing_invite.expires_at.isoformat()  # type: ignore[attr-defined]
    else:
        # 새 초대 코드 생성
        invite_code = secrets.token_urlsafe(32)
        expires_at_dt = datetime.utcnow() + timedelta(hours=body.expires_in_hours)
        
        new_invite = models.Invite(  # type: ignore[call-arg]
            email=body.email,
            invite_code=invite_code,
            used=False,
            created_by=int(current_user.id),  # type: ignore[arg-type,attr-defined]
            expires_at=expires_at_dt
        )
        db.add(new_invite)
        db.commit()
        db.refresh(new_invite)
        
        expires_at = expires_at_dt.isoformat()
    
    # 초대 URL 생성 (프론트엔드 주소)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5500")
    invite_url = f"{frontend_url}/frontend/dashboard/register.html?invite={invite_code}"
    
    return InviteResponse(
        success=True,
        invite_code=invite_code,
        invite_url=invite_url,
        email=body.email,
        expires_at=expires_at
    )


# ========= 초대 코드 검증 =========
class CheckInviteResponse(BaseModel):
    valid: bool
    email: Optional[str] = None
    message: str


@router.get("/check-invite", response_model=CheckInviteResponse)
async def check_invite(
    code: str,
    db: Session = Depends(get_db)
):
    """
    초대 코드 유효성 검사
    - 회원가입 페이지에서 호출
    - 코드가 유효하면 이메일 반환
    """
    invite = db.query(models.Invite).filter(
        models.Invite.invite_code == code
    ).first()
    
    if not invite:
        return CheckInviteResponse(
            valid=False,
            message="유효하지 않은 초대 코드입니다."
        )
    
    # 이미 사용된 코드
    if invite.used:  # type: ignore[attr-defined]
        return CheckInviteResponse(
            valid=False,
            message="이미 사용된 초대 코드입니다."
        )
    
    # 만료된 코드
    if invite.expires_at < datetime.utcnow():  # type: ignore[attr-defined,operator]
        return CheckInviteResponse(
            valid=False,
            message="만료된 초대 코드입니다."
        )
    
    return CheckInviteResponse(
        valid=True,
        email=str(invite.email),  # type: ignore[attr-defined]
        message="유효한 초대 코드입니다."
    )


# ========= 회원가입 =========
class RegisterRequest(BaseModel):
    invite_code: str
    email: str
    name: str
    password: str
    password_confirm: str


@router.post("/register", response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    팀원 회원가입
    - 초대 코드 필수
    - 초대된 이메일과 입력한 이메일 일치 확인
    - 비밀번호 확인 검증
    - 가입 성공 시 자동 로그인 (토큰 발급)
    """
    # 1) 비밀번호 확인 검증
    if body.password != body.password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호가 일치하지 않습니다."
        )
    
    # 2) 비밀번호 길이 검증
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호는 최소 8자 이상이어야 합니다."
        )
    
    # 3) 초대 코드 조회
    invite = db.query(models.Invite).filter(
        models.Invite.invite_code == body.invite_code
    ).first()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효하지 않은 초대 코드입니다."
        )
    
    # 4) 초대 코드 검증
    if invite.used:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 사용된 초대 코드입니다."
        )
    
    if invite.expires_at < datetime.utcnow():  # type: ignore[attr-defined,operator]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="만료된 초대 코드입니다."
        )
    
    # 5) 이메일 일치 확인
    if invite.email != body.email:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="초대된 이메일과 입력한 이메일이 일치하지 않습니다."
        )
    
    # 6) 중복 이메일 체크
    existing_user = db.query(models.User).filter(models.User.email == body.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 가입된 이메일입니다."
        )
    
    # 7) 회원 생성
    hashed_pw = get_password_hash(body.password)
    new_user = models.User(  # type: ignore[call-arg]
        email=body.email,
        name=body.name,
        password_hash=hashed_pw,
        role="agent",  # 초대받은 사용자는 상담원
        is_active=True
    )
    db.add(new_user)
    
    # 8) 초대 코드 사용 처리
    invite.used = True  # type: ignore[attr-defined]
    
    db.commit()
    db.refresh(new_user)
    
    # 9) 자동 로그인 (토큰 발급)
    access_token = create_access_token(data={"sub": str(new_user.id)})  # type: ignore[attr-defined]
    
    return TokenResponse(
        access_token=access_token,
        email=str(new_user.email),  # type: ignore[attr-defined]
        role=str(new_user.role),  # type: ignore[attr-defined]
        user_id=int(new_user.id)  # type: ignore[arg-type,attr-defined]
    )

