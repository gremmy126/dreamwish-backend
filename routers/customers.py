# backend/routers/customers.py
"""
고객 정보 관리 API
- 고객 목록 조회
- 고객 상세 정보 조회
- 고객 정보 수정 (메모, 태그 등)
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from .. import models
from ..auth_utils import get_db, get_current_user

router = APIRouter(prefix="/customers", tags=["Customers"])


# ========= Pydantic 스키마 =========
class CustomerBase(BaseModel):
    external_id: str
    platform: str  # kakao / instagram / facebook / widget
    name: Optional[str] = None
    phone: Optional[str] = None
    profile_image: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    tags: Optional[str] = None  # VIP, 악성고객 등 (콤마 구분)
    memo: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    tags: Optional[str] = None
    memo: Optional[str] = None


class CustomerOut(CustomerBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2


# ========= API 엔드포인트 =========

@router.get("", response_model=List[CustomerOut])
async def get_customers(
    skip: int = 0,
    limit: int = 50,
    platform: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    고객 목록 조회
    - platform 필터 가능 (kakao / instagram / facebook / widget)
    """
    query = db.query(models.Customer)
    
    if platform:
        query = query.filter(models.Customer.platform == platform)
    
    customers = query.order_by(models.Customer.created_at.desc()).offset(skip).limit(limit).all()
    return customers


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    특정 고객 상세 정보 조회
    """
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="고객을 찾을 수 없습니다."
        )
    
    return customer


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    새 고객 생성 (주로 Webhook에서 자동 호출됨)
    - 같은 external_id + platform 조합이 있으면 중복 에러
    """
    # 중복 체크
    existing = db.query(models.Customer).filter(
        models.Customer.external_id == body.external_id,
        models.Customer.platform == body.platform
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 존재하는 고객입니다."
        )
    
    customer = models.Customer(  # type: ignore[call-arg]
        external_id=body.external_id,
        platform=body.platform,
        name=body.name,
        phone=body.phone,
        profile_image=body.profile_image,
        gender=body.gender,
        age=body.age,
        tags=body.tags,
        memo=body.memo
    )
    
    db.add(customer)
    db.commit()
    db.refresh(customer)
    
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: int,
    body: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    고객 정보 수정
    - 상담원이 메모, 태그 등을 업데이트
    """
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="고객을 찾을 수 없습니다."
        )
    
    # 업데이트할 필드만 변경
    update_data = body.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    
    customer.updated_at = datetime.utcnow()  # type: ignore[attr-defined]
    
    db.commit()
    db.refresh(customer)
    
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    고객 삭제 (관리자 전용)
    """
    if str(current_user.role) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다."
        )
    
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="고객을 찾을 수 없습니다."
        )
    
    db.delete(customer)
    db.commit()
    
    return None


@router.get("/search/by-external-id")
async def search_customer_by_external_id(
    external_id: str,
    platform: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    external_id + platform으로 고객 검색
    - Webhook에서 메시지 수신 시 기존 고객 찾기 용도
    """
    customer = db.query(models.Customer).filter(
        models.Customer.external_id == external_id,
        models.Customer.platform == platform
    ).first()
    
    if not customer:
        return {"exists": False, "customer": None}
    
    return {
        "exists": True,
        "customer": CustomerOut.model_validate(customer)
    }
