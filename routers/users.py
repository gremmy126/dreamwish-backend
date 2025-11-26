# backend/routers/users.py
"""
팀원 관리 API
- 관리자가 팀원 목록 조회
- 팀원 활성화/비활성화
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from .. import models
from ..auth_utils import get_db, get_current_user, get_current_admin

router = APIRouter(prefix="/api/users", tags=["Users"])


class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    role: str
    is_active: bool
    created_at: str
    last_login_at: Optional[str] = None


class UserUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    name: Optional[str] = None


@router.get("", response_model=List[UserResponse])
async def get_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # 모든 로그인 사용자 허용
):
    """
    팀원 목록 조회
    - 모든 로그인한 사용자가 조회 가능
    - 관리만 관리 기능 사용 가능 (프론트엔드에서 제어)
    """
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    
    return [
        UserResponse(
            id=int(user.id),  # type: ignore[arg-type,attr-defined]
            email=str(user.email),  # type: ignore[attr-defined]
            name=str(user.name) if user.name else None,  # type: ignore[attr-defined]
            role=str(user.role),  # type: ignore[attr-defined]
            is_active=bool(user.is_active),  # type: ignore[attr-defined]
            created_at=user.created_at.isoformat() if user.created_at else datetime.utcnow().isoformat(),  # type: ignore[attr-defined]
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None  # type: ignore[attr-defined]
        )
        for user in users
    ]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    특정 사용자 정보 조회
    - 관리자는 모든 사용자 조회 가능
    - 일반 사용자는 본인만 조회 가능
    """
    # 권한 체크
    if str(current_user.role) != "admin" and int(current_user.id) != user_id:  # type: ignore[arg-type,attr-defined]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="다른 사용자의 정보를 조회할 권한이 없습니다."
        )
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다."
        )
    
    return UserResponse(
        id=int(user.id),  # type: ignore[arg-type,attr-defined]
        email=str(user.email),  # type: ignore[attr-defined]
        name=str(user.name) if user.name else None,  # type: ignore[attr-defined]
        role=str(user.role),  # type: ignore[attr-defined]
        is_active=bool(user.is_active),  # type: ignore[attr-defined]
        created_at=user.created_at.isoformat() if user.created_at else datetime.utcnow().isoformat(),  # type: ignore[attr-defined]
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None  # type: ignore[attr-defined]
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    """
    사용자 정보 수정
    - 관리자만 다른 사용자 수정 가능
    - is_active: 활성화/비활성화
    - name: 이름 변경
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다."
        )
    
    # 관리자 본인은 비활성화 불가
    if str(user.role) == "admin" and body.is_active is False:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="관리자 계정은 비활성화할 수 없습니다."
        )
    
    # 업데이트
    if body.is_active is not None:
        user.is_active = body.is_active  # type: ignore[attr-defined]
    
    if body.name is not None:
        user.name = body.name  # type: ignore[attr-defined]
    
    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=int(user.id),  # type: ignore[arg-type,attr-defined]
        email=str(user.email),  # type: ignore[attr-defined]
        name=str(user.name) if user.name else None,  # type: ignore[attr-defined]
        role=str(user.role),  # type: ignore[attr-defined]
        is_active=bool(user.is_active),  # type: ignore[attr-defined]
        created_at=user.created_at.isoformat() if user.created_at else datetime.utcnow().isoformat(),  # type: ignore[attr-defined]
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None  # type: ignore[attr-defined]
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    """
    사용자 삭제
    - 관리자만 가능
    - 관리자 본인은 삭제 불가
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다."
        )
    
    # 관리자는 삭제 불가
    if str(user.role) == "admin":  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="관리자 계정은 삭제할 수 없습니다."
        )
    
    # 본인 삭제 불가
    if int(user.id) == int(current_user.id):  # type: ignore[arg-type,attr-defined]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="본인 계정은 삭제할 수 없습니다."
        )
    
    db.delete(user)
    db.commit()
    
    return {
        "success": True,
        "message": "사용자가 삭제되었습니다."
    }

