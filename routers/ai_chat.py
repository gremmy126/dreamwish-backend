# backend/routers/ai_chat.py
"""
AI 채팅 전용 엔드포인트
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .. import models
from ..auth_utils import get_db, get_current_user
from ..services.ollama_chatbot import ollama_chatbot
from ..services.ollama_knowledge_base import ollama_knowledge_base

router = APIRouter(prefix="/api/ai", tags=["AI Chat"])


class AIChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] | None = None


@router.post("/chat")
async def ai_chat(
    request: AIChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    AI와 대화하기 (지식베이스 기반 RAG)
    """
    try:
        user_message = request.message.strip()
        if not user_message:
            raise HTTPException(status_code=400, detail="메시지가 비어있습니다")
        
        print(f"💬 AI 채팅 요청: {user_message[:50]}...")
        
        # 대화 히스토리 (옵션)
        history = request.conversation_history or []
        
        # RAG: 지식베이스에서 관련 정보 검색
        context = ollama_knowledge_base.get_context_for_query(user_message)
        
        # AI 응답 생성
        ai_response = await ollama_chatbot.get_response(
            user_message,
            conversation_history=history,
            context=context
        )
        
        if not ai_response:
            ai_response = "죄송합니다. 답변을 생성할 수 없습니다. 다시 질문해 주세요."
        
        print(f"🤖 AI 응답: {ai_response[:100]}...")
        
        return {
            "status": "success",
            "response": ai_response,
            "context_used": bool(context)
        }
    
    except Exception as e:
        print(f"❌ AI 채팅 오류: {e}")
        raise HTTPException(status_code=500, detail=f"AI 채팅 오류: {str(e)}")


@router.get("/status")
async def ai_status():
    """AI 서비스 상태 확인"""
    return {
        "status": "online",
        "model": "ollama/llama3.2",
        "knowledge_base": "active"
    }
