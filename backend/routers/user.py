# backend/routers/users.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..auth_utils import get_db, get_current_admin

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/")
async def list_users(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(get_current_admin),
):
    """
    관리자만 조회 가능한 유저 목록 API
    - 토큰으로 로그인한 사람이 admin 이 아니면 403 에러
    """
    users = db.query(models.User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "is_active": u.is_active,
        }
        for u in users
    ]
