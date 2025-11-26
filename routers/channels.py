from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Dict
import json

from ..auth_utils import get_db, get_current_user
from .. import models

router = APIRouter(prefix="/api/channels", tags=["Channels"])


class ChannelConnectRequest(BaseModel):
    channel_type: str  # kakao, instagram, facebook, email
    credentials: Dict[str, str]


@router.get("/health")
async def channels_health():
    return {"status": "ok", "router": "channels"}


@router.get("/")
async def list_channels(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    연결된 모든 채널 조회
    """
    channels = db.query(models.Channel).all()
    return [
        {
            "id": ch.id,
            "channel_type": ch.type,  # 모델의 'type' 컬럼
            "name": ch.name,
            "is_active": ch.is_active,
            "created_at": ch.created_at.isoformat() if hasattr(ch.created_at, 'isoformat') else None
        }
        for ch in channels
    ]


@router.post("/connect")
async def connect_channel(
    body: ChannelConnectRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    새 채널 연결
    """
    # 기존 채널이 있는지 확인
    existing = db.query(models.Channel).filter(
        models.Channel.type == body.channel_type  # 모델의 'type' 컬럼
    ).first()
    
    if existing:
        # 업데이트
        existing.config_json = json.dumps(body.credentials)  # type: ignore  # 모델의 'config_json' 컬럼
        existing.is_active = True  # type: ignore
        db.commit()
        db.refresh(existing)
        return {"success": True, "message": "채널이 업데이트되었습니다", "channel_id": existing.id}
    else:
        # 새로 생성
        new_channel = models.Channel(
            type=body.channel_type,  # 모델의 'type' 컬럼
            name=f"{body.channel_type.capitalize()} 채널",
            config_json=json.dumps(body.credentials),  # 모델의 'config_json' 컬럼
            is_active=True
        )
        db.add(new_channel)
        db.commit()
        db.refresh(new_channel)
        return {"success": True, "message": "채널이 연결되었습니다", "channel_id": new_channel.id}


@router.delete("/{channel_id}")
async def disconnect_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    채널 연결 해제
    """
    channel = db.query(models.Channel).filter(models.Channel.id == channel_id).first()
    
    if not channel:
        raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다")
    
    channel.is_active = False  # type: ignore
    db.commit()
    
    return {"success": True, "message": "채널 연결이 해제되었습니다"}
