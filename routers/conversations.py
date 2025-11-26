# backend/routers/conversations.py
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from .. import models
from ..auth_utils import get_db, get_current_user

router = APIRouter(prefix="/conversations", tags=["Conversations"])


# ==== Pydantic 응답 스키마 ====
class ConversationOut(BaseModel):
    id: int
    customer_id: int  # Customer 테이블의 ID
    channel_type: str
    status: str
    profile_name: Optional[str] = None
    profile_image: Optional[str] = None
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    has_ai_response: bool = False  # AI 응답 포함 여부
    ai_response_count: int = 0  # AI 응답 개수

    class Config:
        from_attributes = True  # Pydantic v2


class ConversationDetail(BaseModel):
    id: int
    customer_id: int
    channel_type: str
    status: str
    profile_name: Optional[str] = None
    profile_image: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_type: str
    sender_id: Optional[int] = None
    content: str
    channel: str
    created_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2


# ==== 대화방 목록 ====
@router.get("/", response_model=List[ConversationOut])
def list_conversations(
    channel: Optional[str] = None,  # 채널 필터: kakao, instagram, facebook, widget
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    상담원이 볼 수 있는 대화방 목록.
    - channel 파라미터로 특정 채널만 필터링 가능
    - 최신 생성순으로 정렬
    - last_message, last_message_at 포함
    """
    query = db.query(models.Conversation).options(
        joinedload(models.Conversation.messages)
    )
    
    # 채널 필터링
    if channel and channel != "all":
        query = query.filter(models.Conversation.channel_type == channel)
    
    conversations = (
        query.order_by(models.Conversation.created_at.desc())
        .limit(100)
        .all()
    )

    results: List[ConversationOut] = []
    for conv in conversations:
        # 마지막 메시지 하나 뽑기
        last_msg = None
        last_time = None
        ai_count = 0
        
        if conv.messages:
            last = sorted(conv.messages, key=lambda m: m.created_at)[-1]
            last_msg = last.content
            last_time = last.created_at
            # AI 응답 개수 계산
            ai_count = len([m for m in conv.messages if m.sender_type == "bot"])

        results.append(
            ConversationOut(
                id=int(conv.id),  # type: ignore[arg-type]
                customer_id=int(conv.customer_id),  # type: ignore[arg-type]
                channel_type=str(conv.channel_type),
                status=str(conv.status),
                profile_name=str(conv.profile_name) if conv.profile_name is not None else None,  # type: ignore[arg-type]
                profile_image=str(conv.profile_image) if conv.profile_image is not None else None,  # type: ignore[arg-type]
                last_message=last_msg,
                last_message_at=last_time,
                has_ai_response=ai_count > 0,
                ai_response_count=ai_count
            )
        )

    return results


# ==== 대화방 삭제 ====
@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    대화방 삭제 (메시지도 함께 삭제)
    """
    conversation = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="대화방을 찾을 수 없습니다")
    
    # 관련 메시지 먼저 삭제
    db.query(models.Message).filter(
        models.Message.conversation_id == conversation_id
    ).delete()
    
    # 대화방 삭제
    db.delete(conversation)
    db.commit()
    
    return {"success": True, "message": "대화방이 삭제되었습니다"}


# ==== 특정 대화방 상세 정보 ====
@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    특정 대화방 상세 정보 조회
    """
    conv = (
        db.query(models.Conversation)
        .filter(models.Conversation.id == conversation_id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="대화방을 찾을 수 없습니다.",
        )

    return conv


# ==== 특정 대화방의 메시지 목록 ====
@router.get("/{conversation_id}/messages", response_model=List[MessageOut])
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    특정 conversation 에 속한 메시지 전체 조회 (최신 순)
    """
    conv = (
        db.query(models.Conversation)
        .filter(models.Conversation.id == conversation_id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="대화방을 찾을 수 없습니다.",
        )

    messages = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conversation_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )

    return messages


# ==== 상담 연결 ====
@router.post("/{conversation_id}/connect")
async def connect_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    상담 연결: 상담원이 고객과 대화를 시작함
    - 고객에게 "상담원이 연결되었습니다" 메시지 전송
    - 대화방 상태를 'connected'로 변경
    """
    conv = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id
    ).first()
    
    if not conv:
        raise HTTPException(status_code=404, detail="대화방을 찾을 수 없습니다")
    
    # 대화방 상태 업데이트
    conv.status = "connected"  # type: ignore[attr-defined]
    conv.agent_id = current_user.id  # type: ignore[attr-defined]
    db.commit()
    
    # 시스템 메시지 저장
    system_msg = models.Message(  # type: ignore[call-arg]
        conversation_id=conversation_id,
        sender_type="system",
        sender_id=None,
        content=f"✅ {current_user.name or current_user.email} 상담원이 연결되었습니다.",
        channel=conv.channel_type  # type: ignore[attr-defined]
    )
    db.add(system_msg)
    db.commit()
    db.refresh(system_msg)
    
    # 고객에게 실제로 메시지 전송 (채널별 분기)
    from ..services.kakao_service import send_kakao_message
    from ..services.instagram_service import send_instagram_message
    from ..services.facebook_service import send_facebook_message
    from ..websocket import manager
    import json
    
    # Customer 정보 조회
    customer = db.query(models.Customer).filter(
        models.Customer.id == conv.customer_id  # type: ignore[attr-defined]
    ).first()
    
    if customer:
        message_text = f"✅ {current_user.name or current_user.email} 상담원이 연결되었습니다. 무엇을 도와드릴까요?"
        
        # 채널별 메시지 전송
        if conv.channel_type == "kakao":  # type: ignore[attr-defined]
            # 카카오톡은 스킬 서버 응답 형태로만 가능 (Push 불가능)
            pass
        elif conv.channel_type == "instagram":  # type: ignore[attr-defined]
            await send_instagram_message(customer.external_id, message_text)  # type: ignore[attr-defined]
        elif conv.channel_type == "facebook":  # type: ignore[attr-defined]
            await send_facebook_message(customer.external_id, message_text)  # type: ignore[attr-defined]
        elif conv.channel_type == "widget":  # type: ignore[attr-defined]
            # 웹 위젯: WebSocket으로 전송
            await manager.broadcast_to_agents(json.dumps({  # type: ignore[arg-type]
                "type": "agent_reply_sent",
                "conversation_id": conversation_id,
                "message": {
                    "id": system_msg.id,  # type: ignore[attr-defined]
                    "content": message_text,
                    "sender_type": "system",
                    "created_at": system_msg.created_at.isoformat()  # type: ignore[attr-defined]
                }
            }))
    
    return {
        "success": True,
        "message": "상담이 연결되었습니다",
        "conversation_id": conversation_id,
        "agent_name": current_user.name or current_user.email
    }


# ==== 상담 종료 ====
@router.post("/{conversation_id}/end")
async def end_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    상담 종료: 대화를 완료하고 상태를 'closed'로 변경
    """
    conv = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id
    ).first()
    
    if not conv:
        raise HTTPException(status_code=404, detail="대화방을 찾을 수 없습니다")
    
    # 대화방 상태 업데이트
    conv.status = "closed"  # type: ignore[attr-defined]
    db.commit()
    
    # 시스템 메시지 저장
    system_msg = models.Message(  # type: ignore[call-arg]
        conversation_id=conversation_id,
        sender_type="system",
        sender_id=None,
        content="⭕ 상담이 종료되었습니다. 감사합니다!",
        channel=conv.channel_type  # type: ignore[attr-defined]
    )
    db.add(system_msg)
    db.commit()
    db.refresh(system_msg)
    
    # WebSocket으로 알림
    from ..websocket import manager
    import json
    
    await manager.broadcast_to_agents(json.dumps({  # type: ignore[arg-type]
        "type": "conversation_updated",
        "conversation_id": conversation_id,
        "status": "closed"
    }))
    
    return {
        "success": True,
        "message": "상담이 종료되었습니다",
        "conversation_id": conversation_id
    }
