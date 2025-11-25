# backend/services/agent_assignment.py
"""
상담원 자동 배정 서비스
- 라운드 로빈 방식
- 동시 상담 수 제한
- 우선순위 처리
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime
from .. import models


class AgentAssignmentService:
    """상담원 자동 배정 관리"""
    
    @staticmethod
    def get_available_agents(db: Session):
        """
        현재 사용 가능한 상담원 목록 조회
        - 온라인 상태
        - 자동 배정 허용
        - 최대 동시 상담 수 미달
        """
        # 온라인 상태이고 자동 배정이 활성화된 상담원
        agents = db.query(models.User).filter(
            models.User.role == "agent",
            models.User.is_active == True,
            models.User.status == "online",
            models.User.auto_assign == True
        ).all()
        
        available = []
        for agent in agents:
            # 현재 담당 중인 열린 대화 수
            current_chats = db.query(func.count(models.Conversation.id)).filter(
                models.Conversation.assigned_agent_id == agent.id,
                models.Conversation.status == "open"
            ).scalar()
            
            # 최대 동시 상담 수 체크
            if current_chats < agent.max_concurrent_chats:
                available.append({
                    "agent": agent,
                    "current_load": current_chats,
                    "capacity": agent.max_concurrent_chats
                })
        
        # 부하가 적은 순서로 정렬
        available.sort(key=lambda x: x["current_load"])
        return available
    
    @staticmethod
    def assign_agent_to_conversation(db: Session, conversation_id: int) -> bool:
        """
        대화방에 상담원 자동 배정
        
        Returns:
            bool: 배정 성공 여부
        """
        conversation = db.query(models.Conversation).filter(
            models.Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            return False
        
        # 이미 배정된 경우
        if conversation.assigned_agent_id is not None:  # type: ignore
            return True
        
        # 사용 가능한 상담원 조회
        available_agents = AgentAssignmentService.get_available_agents(db)
        
        if not available_agents:
            print(f"⚠️ 사용 가능한 상담원이 없습니다. 대화방 {conversation_id}")
            return False
        
        # 가장 부하가 적은 상담원에게 배정
        selected = available_agents[0]
        agent = selected["agent"]
        
        conversation.assigned_agent_id = agent.id  # type: ignore
        conversation.assigned_at = datetime.utcnow()  # type: ignore
        conversation.status = "open"  # type: ignore
        
        db.commit()
        
        print(f"✅ 대화방 {conversation_id} → 상담원 {agent.name} ({agent.email}) 배정")
        print(f"   현재 부하: {selected['current_load']}/{selected['capacity']}")
        
        return True
    
    @staticmethod
    def reassign_agent(db: Session, conversation_id: int, new_agent_id: int) -> bool:
        """
        대화방 상담원 재배정
        
        Args:
            conversation_id: 대화방 ID
            new_agent_id: 새 상담원 ID
        
        Returns:
            bool: 재배정 성공 여부
        """
        conversation = db.query(models.Conversation).filter(
            models.Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            return False
        
        new_agent = db.query(models.User).filter(
            models.User.id == new_agent_id,
            models.User.role == "agent"
        ).first()
        
        if not new_agent:
            return False
        
        old_agent_id = conversation.assigned_agent_id
        conversation.assigned_agent_id = new_agent_id  # type: ignore
        conversation.assigned_at = datetime.utcnow()  # type: ignore
        
        db.commit()
        
        print(f"✅ 대화방 {conversation_id} 재배정: {old_agent_id} → {new_agent_id}")
        
        return True
    
    @staticmethod
    def get_agent_statistics(db: Session, agent_id: int):
        """
        상담원 통계 조회
        - 현재 담당 대화 수
        - 오늘 처리한 대화 수
        - 평균 응답 시간
        """
        # 현재 열린 대화 수
        active_chats = db.query(func.count(models.Conversation.id)).filter(
            models.Conversation.assigned_agent_id == agent_id,
            models.Conversation.status == "open"
        ).scalar()
        
        # 오늘 종료한 대화 수
        from datetime import date
        today_start = datetime.combine(date.today(), datetime.min.time())
        
        closed_today = db.query(func.count(models.Conversation.id)).filter(
            models.Conversation.assigned_agent_id == agent_id,
            models.Conversation.status == "closed",
            models.Conversation.updated_at >= today_start
        ).scalar()
        
        # 전체 메시지 수
        total_messages = db.query(func.count(models.Message.id)).filter(
            models.Message.sender_type == "agent",
            models.Message.sender_id == agent_id
        ).scalar()
        
        return {
            "active_chats": active_chats or 0,
            "closed_today": closed_today or 0,
            "total_messages": total_messages or 0
        }
