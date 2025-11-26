# backend/routers/reply.py
"""
통합 답장 API
상담원이 대시보드에서 메시지를 보내면 자동으로 채널별 발송
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from .. import models
from ..auth_utils import get_db, get_current_user
from ..websocket import manager
from ..services.kakao_service import send_kakao_message
from ..services.instagram_service import send_instagram_message
from ..services.facebook_service import send_facebook_message

router = APIRouter(prefix="/api/reply", tags=["Reply"])


class ReplyRequest(BaseModel):
    conversation_id: int
    message: str


@router.post("")
async def send_reply(
    body: ReplyRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    상담원이 고객에게 답장 (채널 자동 라우팅)
    
    1. conversation 조회 → channel_type 확인
    2. channel_type에 맞는 서비스로 발송
    3. DB에 Message(sender_type='agent') 저장
    4. WebSocket으로 실시간 업데이트
    """
    
    # 1) Conversation 조회
    conversation = db.query(models.Conversation).filter(
        models.Conversation.id == body.conversation_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")
    
    # 2) Customer 정보 조회
    customer = db.query(models.Customer).filter(
        models.Customer.id == conversation.customer_id
    ).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="고객 정보를 찾을 수 없습니다")
    
    # 3) 채널별 메시지 발송
    channel_type = conversation.channel_type  # type: ignore[assignment]
    success = False
    error_message = None
    
    try:
        if str(channel_type) == "kakao":  # type: ignore[comparison-overlap]
            # 카카오톡 발송
            await send_kakao_message(
                message=body.message,
                recipient_id=str(customer.external_id),  # type: ignore[arg-type]
                db=db
            )
            success = True
            
        elif str(channel_type) == "instagram":  # type: ignore[comparison-overlap]
            # 인스타그램 DM 발송
            await send_instagram_message(
                message=body.message,
                recipient_id=str(customer.external_id),  # type: ignore[arg-type]
                db=db
            )
            success = True
            
        elif str(channel_type) == "facebook":  # type: ignore[comparison-overlap]
            # 페이스북 메신저 발송
            await send_facebook_message(
                message=body.message,
                recipient_id=str(customer.external_id),  # type: ignore[arg-type]
                db=db
            )
            success = True
            
        elif str(channel_type) == "widget":  # type: ignore[comparison-overlap]
            # 웹 위젯 발송 (WebSocket으로만 전송)
            from ..websocket import manager
            # send_to_widget 메서드 직접 호출
            widget_id = f"widget_{customer.external_id}"  # type: ignore[str-bytes-safe]
            if widget_id in manager.active_connections:
                import json
                await manager.active_connections[widget_id].send_text(json.dumps({
                    "type": "agent_message",
                    "content": body.message,
                    "agent_name": current_user.username,  # type: ignore[attr-defined]
                    "timestamp": datetime.now().isoformat()
                }))
            success = True
            
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"지원하지 않는 채널입니다: {channel_type}"
            )
            
    except Exception as e:
        error_message = str(e)
        success = False
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"메시지 발송 실패: {error_message or '알 수 없는 오류'}"
        )
    
    # 4) DB에 메시지 저장
    message = models.Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=current_user.id,
        content=body.message,
        channel=channel_type
    )
    db.add(message)
    
    # 5) Conversation 업데이트
    # conversation.updated_at = datetime.now()  # SQLAlchemy가 자동 업데이트
    
    db.commit()
    db.refresh(message)
    
    # 6) WebSocket으로 대시보드에 실시간 업데이트
    import json
    await manager.broadcast_to_agents(json.dumps({  # type: ignore[arg-type]
        "type": "agent_reply_sent",
        "conversation_id": int(conversation.id),  # type: ignore[arg-type]
        "message": {
            "id": int(message.id),  # type: ignore[arg-type]
            "content": body.message,
            "sender_type": "agent",
            "sender_name": current_user.username,  # type: ignore[attr-defined]
            "created_at": message.created_at.isoformat()  # type: ignore[attr-defined]
        }
    }))
    
    return {
        "success": True,
        "message_id": int(message.id),  # type: ignore[arg-type]
        "channel": str(channel_type),
        "timestamp": message.created_at.isoformat()  # type: ignore[attr-defined]
    }
