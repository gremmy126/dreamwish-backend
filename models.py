# backend/models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """
    상담원 / 관리자 겸용 유저 모델
    - 로그인한 사람 = 팀원
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="agent")  # "admin" or "agent"
    is_active = Column(Boolean, default=True)
    
    # 상담원 상태 관리
    status = Column(String(50), default="offline")  # online / offline / away / busy
    auto_assign = Column(Boolean, default=True)  # 자동 배정 허용 여부
    max_concurrent_chats = Column(Integer, default=5)  # 동시 상담 최대 개수
    
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    # 관계
    messages = relationship("Message", back_populates="sender_user")
    assigned_conversations = relationship("Conversation", back_populates="assigned_agent")


class Invite(Base):
    """
    팀원 초대 코드 테이블
    - 관리자가 초대 링크를 생성하면 여기에 저장
    - 초대받은 사람이 회원가입 시 코드를 확인
    """
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)  # 초대받은 이메일
    invite_code = Column(String(255), unique=True, nullable=False, index=True)  # 초대 코드
    used = Column(Boolean, default=False)  # 사용 여부
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 초대한 관리자
    
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # 만료 시간 (24시간~7일 등)


class Customer(Base):
    """
    고객 정보 통합 테이블
    - 카카오/인스타/페북/웹 위젯 등 여러 채널에서 온 고객을 한 곳에서 관리
    - 같은 고객이 여러 채널로 문의해도 하나의 Customer로 매핑 가능
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(255), index=True, nullable=False)  # SNS 고유 ID or phone or widget cookie
    platform = Column(String(50), nullable=False)  # kakao / instagram / facebook / widget
    name = Column(String(100), nullable=True)  # 고객 이름 또는 닉네임
    phone = Column(String(50), nullable=True)  # 전화번호
    profile_image = Column(Text, nullable=True)  # 프로필 이미지 URL
    gender = Column(String(20), nullable=True)  # 성별
    age = Column(String(20), nullable=True)  # 연령대
    tags = Column(String(255), nullable=True)  # VIP / 악성고객 / 신규고객 / A등급 등 (콤마 구분)
    memo = Column(Text, nullable=True)  # 상담원 메모

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계: 이 고객의 모든 대화방들
    conversations = relationship("Conversation", back_populates="customer")


class Conversation(Base):
    """
    하나의 고객 문의 방 (위젯/카카오/인스타 상관없이)
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)  # Customer 테이블 연결
    channel_type = Column(String(50), default="widget")  # widget/kakao/instagram/facebook
    status = Column(String(50), default="open")  # open/closed/waiting
    
    # 상담원 배정
    assigned_agent_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    assigned_at = Column(DateTime, nullable=True)
    priority = Column(Integer, default=0)  # 우선순위 (높을수록 우선)
    
    # 읽음 상태
    unread_count = Column(Integer, default=0)  # 안 읽은 메시지 수
    last_message_at = Column(DateTime, nullable=True)  # 마지막 메시지 시간
    
    # 채널별 추가 정보
    profile_name = Column(String(100), nullable=True)  # 대화방 표시용 이름 (고객명)
    profile_image = Column(Text, nullable=True)  # 프로필 이미지 URL

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계
    customer = relationship("Customer", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")
    assigned_agent = relationship("User", back_populates="assigned_conversations")


class Message(Base):
    """
    실제 채팅 메시지
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    sender_type = Column(String(50), default="customer")  # customer/agent/bot/system
    # 에이전트인 경우 User.id, 고객/봇이면 None 가능
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)

    # 메시지 타입 및 파일 정보
    message_type = Column(String(50), default="text")  # text/image/video/file/button/sticker
    file_url = Column(Text, nullable=True)  # 파일/이미지 URL
    file_type = Column(String(50), nullable=True)  # image/jpeg, video/mp4, application/pdf 등
    file_size = Column(Integer, nullable=True)  # 파일 크기 (bytes)
    thumbnail_url = Column(Text, nullable=True)  # 썸네일 URL (이미지/비디오)
    
    # 메시지 상태 추적
    status = Column(String(50), default="sent")  # sent/delivered/read/failed
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    
    # 어떤 채널(웹/카카오/인스타/이메일 등)에서 온 메시지인지
    channel = Column(String(50), default="web")

    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    sender_user = relationship("User", back_populates="messages")


class Channel(Base):
    """
    카카오/인스타/페북/이메일 채널 정보
    """
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(50), nullable=False)  # kakao/instagram/facebook/email 등
    name = Column(String(100), nullable=False)  # 관리자 눈에 보이는 이름
    config_json = Column(Text, nullable=True)  # 토큰/키 등 JSON 문자열
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class BusinessHours(Base):
    """
    운영시간 관리 테이블
    - 요일별 운영 시간 설정
    - 운영시간 외 자동 응답 처리
    """
    __tablename__ = "business_hours"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=월요일, 6=일요일
    open_time = Column(String(5), nullable=False)  # "09:00"
    close_time = Column(String(5), nullable=False)  # "18:00"
    is_active = Column(Boolean, default=True)
    timezone = Column(String(50), default="Asia/Seoul")
    
    # 특별 운영 (공휴일 등)
    special_date = Column(DateTime, nullable=True)  # 특정 날짜
    special_message = Column(Text, nullable=True)  # 특별 안내 메시지
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MessageTemplate(Base):
    """
    응답 템플릿 관리
    - 자주 사용하는 답변 템플릿
    - 빠른 응답을 위한 FAQ
    """
    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)  # 템플릿 제목
    content = Column(Text, nullable=False)  # 템플릿 내용
    category = Column(String(100), nullable=True)  # 카테고리 (인사/문의응답/종료 등)
    shortcut = Column(String(50), nullable=True)  # 단축키 (예: /hello)
    usage_count = Column(Integer, default=0)  # 사용 횟수
    
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FileUpload(Base):
    """
    파일 업로드 관리
    - 고객/상담원이 업로드한 파일 추적
    - 클라우드 스토리지 URL 관리
    """
    __tablename__ = "file_uploads"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)  # 실제 저장된 파일명
    file_path = Column(Text, nullable=False)  # 로컬 또는 클라우드 경로
    file_url = Column(Text, nullable=True)  # 공개 URL
    file_type = Column(String(100), nullable=False)  # MIME type
    file_size = Column(Integer, nullable=False)  # bytes
    
    uploaded_by_type = Column(String(50), nullable=False)  # customer/agent
    uploaded_by_id = Column(String(255), nullable=True)  # User ID 또는 Customer external_id
    
    created_at = Column(DateTime, default=datetime.utcnow)
