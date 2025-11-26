# backend/routers/agent.py
"""
상담원 관리 API
- 상담원 상태 관리
- 대화방 배정/재배정
- 통계 조회
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from .. import models
from ..auth_utils import get_db, get_current_user
from ..services.agent_assignment import AgentAssignmentService
from ..websocket import manager
import json

router = APIRouter(prefix="/api/agent", tags=["Agent"])


class AgentStatusUpdate(BaseModel):
    status: str  # online / offline / away / busy


class AssignAgentRequest(BaseModel):
    conversation_id: int
    agent_id: int


@router.post("/status")
async def update_agent_status(
    body: AgentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    상담원 상태 업데이트
    """
    valid_statuses = ["online", "offline", "away", "busy"]
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 상태입니다. 사용 가능: {', '.join(valid_statuses)}"
        )
    
    current_user.status = body.status  # type: ignore
    current_user.last_login_at = datetime.utcnow()  # type: ignore
    
    db.commit()
    
    # WebSocket으로 다른 상담원들에게 알림
    await manager.broadcast_to_agents(json.dumps({
        "type": "agent_status_changed",
        "agent_id": current_user.id,
        "agent_name": current_user.name,
        "status": body.status
    }))
    
    return {
        "success": True,
        "agent_id": current_user.id,
        "status": body.status
    }


@router.get("/available")
async def get_available_agents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    사용 가능한 상담원 목록 조회
    """
    available_agents = AgentAssignmentService.get_available_agents(db)
    
    result = []
    for item in available_agents:
        agent = item["agent"]
        result.append({
            "agent_id": agent.id,
            "name": agent.name,
            "email": agent.email,
            "status": agent.status,
            "current_load": item["current_load"],
            "capacity": item["capacity"]
        })
    
    return {
        "available_agents": result,
        "total": len(result)
    }


@router.post("/assign")
async def assign_agent(
    body: AssignAgentRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    대화방에 상담원 수동 배정
    """
    # 관리자만 재배정 가능
    if current_user.role != "admin":  # type: ignore
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    
    success = AgentAssignmentService.reassign_agent(
        db,
        body.conversation_id,
        body.agent_id
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="배정 실패")
    
    # 배정된 상담원에게 WebSocket 알림
    conversation = db.query(models.Conversation).filter(
        models.Conversation.id == body.conversation_id
    ).first()
    
    if conversation:
        await manager.broadcast_to_agents(json.dumps({
            "type": "conversation_assigned",
            "conversation_id": body.conversation_id,
            "agent_id": body.agent_id,
            "customer_name": conversation.profile_name
        }))
    
    return {
        "success": True,
        "conversation_id": body.conversation_id,
        "agent_id": body.agent_id
    }


@router.get("/statistics")
async def get_agent_statistics(
    agent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    상담원 통계 조회
    """
    # agent_id가 없으면 현재 사용자 통계
    target_id = agent_id or current_user.id
    
    stats = AgentAssignmentService.get_agent_statistics(db, int(target_id))  # type: ignore
    
    return {
        "agent_id": target_id,
        "statistics": stats
    }


@router.get("/my-conversations")
async def get_my_conversations(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    내가 담당 중인 대화방 목록
    """
    query = db.query(models.Conversation).filter(
        models.Conversation.assigned_agent_id == current_user.id
    )
    
    if status:
        query = query.filter(models.Conversation.status == status)
    
    conversations = query.order_by(
        models.Conversation.last_message_at.desc()
    ).all()
    
    result = []
    for conv in conversations:
        customer = db.query(models.Customer).filter(
            models.Customer.id == conv.customer_id
        ).first()
        
        # 마지막 메시지
        last_message = db.query(models.Message).filter(
            models.Message.conversation_id == conv.id
        ).order_by(models.Message.created_at.desc()).first()
        
        result.append({
            "conversation_id": conv.id,
            "customer_name": customer.name if customer else "Unknown",
            "channel_type": conv.channel_type,
            "status": conv.status,
            "unread_count": conv.unread_count,
            "last_message": {
                "content": last_message.content if last_message else "",
                "created_at": last_message.created_at.isoformat() if last_message else None
            },
            "assigned_at": conv.assigned_at.isoformat() if conv.assigned_at is not None else None  # type: ignore
        })
    
    return {
        "conversations": result,
        "total": len(result)
    }
