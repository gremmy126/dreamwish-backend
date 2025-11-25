# backend/services/business_hours.py
"""
운영시간 관리 서비스
- 운영시간 체크
- 운영시간 외 자동 응답
"""

from sqlalchemy.orm import Session
from datetime import datetime, time
import pytz
from .. import models


class BusinessHoursService:
    """운영시간 관리"""
    
    @staticmethod
    def is_business_hours(db: Session, timezone: str = "Asia/Seoul") -> bool:
        """
        현재 운영시간인지 확인
        
        Returns:
            bool: 운영시간이면 True, 아니면 False
        """
        # 현재 시간 (timezone 적용)
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        current_time = now.time()
        current_day = now.weekday()  # 0=월요일, 6=일요일
        
        # 해당 요일의 운영시간 조회
        business_hour = db.query(models.BusinessHours).filter(
            models.BusinessHours.day_of_week == current_day,
            models.BusinessHours.is_active == True
        ).first()
        
        if not business_hour:
            # 운영시간 설정이 없으면 기본적으로 운영 중으로 간주
            return True
        
        # 시간 문자열을 time 객체로 변환
        open_time = datetime.strptime(str(business_hour.open_time), "%H:%M").time()  # type: ignore
        close_time = datetime.strptime(str(business_hour.close_time), "%H:%M").time()  # type: ignore
        
        # 운영시간 체크
        if open_time <= current_time <= close_time:
            return True
        
        return False
    
    @staticmethod
    def get_business_hours_message(db: Session) -> str:
        """
        운영시간 안내 메시지 생성
        """
        now = datetime.now()
        current_day = now.weekday()
        
        business_hour = db.query(models.BusinessHours).filter(
            models.BusinessHours.day_of_week == current_day,
            models.BusinessHours.is_active == True
        ).first()
        
        if not business_hour:
            return "현재 운영시간이 아닙니다. 나중에 다시 문의해주세요."
        
        return f"""
안녕하세요! 현재는 운영시간이 아닙니다.

운영시간: {business_hour.open_time} ~ {business_hour.close_time}

운영시간 내에 다시 문의해주시면 상담원이 직접 도와드리겠습니다.
지금은 AI 챗봇이 도움을 드릴 수 있습니다. 궁금하신 점을 말씀해주세요!
        """.strip()
    
    @staticmethod
    def create_default_business_hours(db: Session):
        """
        기본 운영시간 생성 (월~금 9시~18시)
        """
        # 기존 데이터 확인
        existing = db.query(models.BusinessHours).first()
        if existing:
            print("운영시간 설정이 이미 존재합니다.")
            return
        
        # 월~금 (0~4)
        for day in range(5):
            hours = models.BusinessHours(
                day_of_week=day,
                open_time="09:00",
                close_time="18:00",
                is_active=True,
                timezone="Asia/Seoul"
            )
            db.add(hours)
        
        # 토~일 (5~6) - 휴무
        for day in range(5, 7):
            hours = models.BusinessHours(
                day_of_week=day,
                open_time="00:00",
                close_time="00:00",
                is_active=False,
                timezone="Asia/Seoul"
            )
            db.add(hours)
        
        db.commit()
        print("✅ 기본 운영시간 설정 완료 (월~금 9:00-18:00)")
    
    @staticmethod
    def should_auto_respond(db: Session) -> bool:
        """
        AI 자동 응답을 해야 하는지 판단
        
        Returns:
            bool: 자동 응답 필요시 True
        """
        # 운영시간 체크
        is_open = BusinessHoursService.is_business_hours(db)
        
        if not is_open:
            return True
        
        # 운영시간이지만 사용 가능한 상담원이 없는 경우
        from .agent_assignment import AgentAssignmentService
        available_agents = AgentAssignmentService.get_available_agents(db)
        
        if not available_agents:
            return True
        
        return False
