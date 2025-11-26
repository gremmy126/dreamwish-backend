# backend/routers/chat.py

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

from .. import models
from ..auth_utils import get_db
from ..websocket import manager

router = APIRouter(prefix="/api", tags=["Chat"])


class WidgetMessageRequest(BaseModel):
    customer_id: str   # 위젯에서 쓸 고객 식별 ID
    content: str       # 고객이 입력한 메시지


@router.post("/widget-message")
async def widget_message(
    body: WidgetMessageRequest,
    db: Session = Depends(get_db),
):
    """
    위젯에서 온 고객 메시지 처리

    1) customer_id 기준으로 conversation 찾고, 없으면 새로 생성
    2) Message(sender_type='customer') 저장
    3) WebSocket 으로 상담원(연결된 에이전트들)에게 새 메시지 알림 브로드캐스트
    """
    # 1) 기존 대화방 찾기
    conv = (
        db.query(models.Conversation)
        .filter(models.Conversation.customer_id == body.customer_id)
        .first()
    )

    # 없으면 새로 생성
    if conv is None:
        conv = models.Conversation(
            customer_id=body.customer_id,
            channel_type="widget",
            status="open",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # 2) 메시지 저장
    msg = models.Message(
        conversation_id=conv.id,
        sender_type="customer",
        sender_id=None,          # 고객이라 user_id 없음
        content=body.content,
        channel="web",
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # 3) WebSocket 으로 상담 대시보드에 알림
    await manager.broadcast_to_all_agents({
        "type": "new_message",
        "conversation_id": int(conv.id),  # type: ignore[arg-type]
        "content": body.content,
        "sender_type": "customer",
    })

    return {"conversation_id": int(conv.id), "message_id": int(msg.id)}  # type: ignore[arg-type]
