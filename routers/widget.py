# backend/routers/widget.py
"""
고객 위젯용 API
- 인증 없이 접근 가능
- 고객 ID는 브라우저 쿠키/localStorage 기반
- 대시보드 업로드 PDF 기반 AI 자동응답
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import json

from .. import models
from ..auth_utils import get_db
from ..websocket import manager
from ..services.ai_chatbot import AIChatbot
from ..services.ollama_knowledge_base import ollama_knowledge_base

# AI 챗봇 인스턴스 (대시보드 업로드 PDF 기반 지식베이스 사용)
ai_chatbot = AIChatbot()

router = APIRouter(prefix="/widget", tags=["Widget"])


# ========= Pydantic 스키마 =========
class WidgetMessageRequest(BaseModel):
    customer_external_id: str  # 브라우저에서 생성한 고유 ID (uuid 등)
    customer_name: Optional[str] = None
    content: str


class WidgetMessageResponse(BaseModel):
    conversation_id: int
    message_id: int
    status: str


# ========= API 엔드포인트 =========

@router.post("/message", response_model=WidgetMessageResponse)
async def send_widget_message(
    body: WidgetMessageRequest,
    db: Session = Depends(get_db)
):
    """
    위젯에서 고객 메시지 전송
    1. Customer 찾기 or 생성
    2. Conversation 찾기 or 생성 (status=open인 것)
    3. Message 저장
    4. WebSocket으로 상담원에게 알림 (추후 구현)
    """
    
    # 1. Customer 찾기 or 생성
    customer = db.query(models.Customer).filter(
        models.Customer.external_id == body.customer_external_id,
        models.Customer.platform == "widget"
    ).first()
    
    if not customer:
        # 새 고객 생성
        customer = models.Customer(  # type: ignore[call-arg]
            external_id=body.customer_external_id,
            platform="widget",
            name=body.customer_name or f"손님_{body.customer_external_id[:8]}"
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
    
    # 2. 열려있는 Conversation 찾기 or 생성
    conversation = db.query(models.Conversation).filter(
        models.Conversation.customer_id == customer.id,  # type: ignore[attr-defined]
        models.Conversation.status == "open"
    ).first()
    
    if not conversation:
        # 새 대화방 생성
        conversation = models.Conversation(  # type: ignore[call-arg]
            customer_id=customer.id,  # type: ignore[attr-defined]
            channel_type="widget",
            status="open",
            profile_name=customer.name,  # type: ignore[attr-defined]
            profile_image=customer.profile_image  # type: ignore[attr-defined]
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    
    # 3. Message 저장
    message = models.Message(  # type: ignore[call-arg]
        conversation_id=conversation.id,  # type: ignore[attr-defined]
        sender_type="customer",
        sender_id=None,
        content=body.content,
        channel="widget"
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    
    # 3.5) AI 자동 응답 생성 (대시보드 업로드 PDF 기반 지식베이스)
    ai_response = None
    try:
        # 대화 히스토리 가져오기
        history = db.query(models.Message).filter(
            models.Message.conversation_id == conversation.id  # type: ignore[attr-defined]
        ).order_by(models.Message.created_at.desc()).limit(10).all()
        
        history_list = [{
            "sender_type": h.sender_type,  # type: ignore[attr-defined]
            "content": h.content  # type: ignore[attr-defined]
        } for h in reversed(history)]
        
        # RAG: 대시보드 업로드 PDF에서 관련 문서 검색
        context = ollama_knowledge_base.get_context_for_query(body.content)
        
        # AI 응답 생성
        ai_response = await ai_chatbot.get_response_with_context(
            user_message=body.content,
            conversation_history=history_list,
            context=context
        )
        
    except Exception as e:
        print(f"❌ AI 응답 생성 실패: {e}")
        ai_response = None
    
    # AI 응답 저장 및 위젯으로 전송
    if ai_response:
        ai_msg = models.Message(  # type: ignore[call-arg]
            conversation_id=conversation.id,  # type: ignore[attr-defined]
            sender_type="bot",
            sender_id=None,
            content=ai_response,
            channel="widget"
        )
        db.add(ai_msg)
        db.commit()
        db.refresh(ai_msg)
        
        # 위젯으로 AI 응답 전송 (직접 WebSocket 사용)
        widget_id = f"widget_{body.customer_external_id}"
        if widget_id in manager.active_connections:
            import json as json_module
            await manager.active_connections[widget_id].send_text(json_module.dumps({
                "type": "agent_message",
                "content": ai_response,
                "agent_name": "AI 어시스턴트",
                "timestamp": ai_msg.created_at.isoformat(),  # type: ignore[attr-defined]
                "is_bot": True
            }))
        
        print(f"🤖 위젯 AI 자동 응답: {ai_response[:50]}...")
    
    # 4. WebSocket으로 모든 상담원에게 알림
    await manager.broadcast_to_agents(json.dumps({
        "type": "new_customer_message",
        "conversation_id": int(conversation.id),  # type: ignore[attr-defined,arg-type]
        "customer_name": customer.name,  # type: ignore[attr-defined]
        "content": body.content,
        "created_at": message.created_at.isoformat(),  # type: ignore[attr-defined]
        "ai_responded": ai_response is not None
    }))
    
    return WidgetMessageResponse(
        conversation_id=int(conversation.id),  # type: ignore[attr-defined,arg-type]
        message_id=int(message.id),  # type: ignore[attr-defined,arg-type]
        status="sent"
    )


@router.get("/conversation/{external_id}")
async def get_widget_conversation(
    external_id: str,
    db: Session = Depends(get_db)
):
    """
    위젯에서 기존 대화 내역 불러오기
    """
    customer = db.query(models.Customer).filter(
        models.Customer.external_id == external_id,
        models.Customer.platform == "widget"
    ).first()
    
    if not customer:
        return {"exists": False, "messages": []}
    
    conversation = db.query(models.Conversation).filter(
        models.Conversation.customer_id == customer.id,  # type: ignore[attr-defined]
        models.Conversation.status == "open"
    ).first()
    
    if not conversation:
        return {"exists": False, "messages": []}
    
    messages = db.query(models.Message).filter(
        models.Message.conversation_id == conversation.id  # type: ignore[attr-defined]
    ).order_by(models.Message.created_at.asc()).all()
    
    return {
        "exists": True,
        "conversation_id": conversation.id,  # type: ignore[attr-defined]
        "messages": [
            {
                "id": m.id,  # type: ignore[attr-defined]
                "sender_type": m.sender_type,  # type: ignore[attr-defined]
                "content": m.content,  # type: ignore[attr-defined]
                "created_at": m.created_at.isoformat()  # type: ignore[attr-defined]
            }
            for m in messages
        ]
    }
