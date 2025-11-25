# backend/main.py
"""
드림위시 옴니채널 플랫폼 - 메인 서버
"""

from datetime import datetime
import json
import os
from typing import Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import engine, SessionLocal
from . import models
from .models import Message, Channel, Conversation
from .websocket import ConnectionManager
from .routers import chat, channels, webhook, auth, users, conversations, customers, widget, reply, admin, knowledge_base_router, ai_chat

load_dotenv()

# DB 테이블 생성
models.Base.metadata.create_all(bind=engine)

# FastAPI 앱
app = FastAPI(
    title="Dreamwish Omnichannel Platform",
    description="통합 고객 지원 플랫폼",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket 연결 관리자
manager = ConnectionManager()

# 🔹 프로젝트 루트 기준으로 frontend 폴더 경로 계산
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_dir = os.path.join(BASE_DIR, "frontend")
dashboard_dir = os.path.join(frontend_dir, "dashboard")
widget_dir = os.path.join(frontend_dir, "widget")

# 🔹 정적 파일 서빙
app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")
app.mount("/widget", StaticFiles(directory=widget_dir, html=True), name="widget_files")
app.mount("/frontend", StaticFiles(directory=frontend_dir, html=True), name="frontend")

# 라우터
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(customers.router)  # ✅ 고객 관리 라우터 추가
app.include_router(conversations.router)  # ✅ 추가
app.include_router(chat.router)
app.include_router(channels.router)
app.include_router(webhook.router)
app.include_router(widget.router)  # ✅ 위젯 라우터 추가
app.include_router(reply.router)  # ✅ 통합 답장 라우터
app.include_router(admin.router)  # ✅ 관리자 전용 라우터
app.include_router(knowledge_base_router.router)  # ✅ 지식베이스 관리
app.include_router(ai_chat.router)  # ✅ AI 채팅 전용 라우터

# 새로 추가된 라우터
from .routers import upload, agent
app.include_router(upload.router)  # ✅ 파일 업로드
app.include_router(agent.router)  # ✅ 상담원 관리


# DB 의존성
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic 모델
class MessageCreate(BaseModel):
    conversation_id: int
    sender_type: str  # customer, agent, bot
    sender_id: Optional[int] = None
    content: str
    channel: str  # web, kakao, instagram, facebook, email


class ChannelConnect(BaseModel):
    channel_type: str
    name: str = "기본 채널"
    credentials: Dict[str, str]


# 루트 엔드포인트
@app.get("/")
async def root():
    return {
        "message": "Dreamwish Omnichannel Platform",
        "version": "1.0.0",
        "status": "running",
    }


# WebSocket 엔드포인트 - 상담원용
@app.websocket("/ws/agent/{agent_id}")
async def agent_websocket(websocket: WebSocket, agent_id: str):
    """
    상담원 대시보드용 WebSocket
    - 고객 메시지 실시간 수신
    - 다른 상담원 메시지 수신
    """
    await manager.connect(websocket, f"agent_{agent_id}")

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            msg_type = message_data.get("type")
            
            if msg_type == "agent_reply":
                # 상담원이 고객에게 답장
                await handle_agent_reply(message_data, agent_id)
            elif msg_type == "heartbeat":
                # 상담원 접속 상태 유지
                pass

    except WebSocketDisconnect:
        manager.disconnect(f"agent_{agent_id}")


# WebSocket 엔드포인트 - 위젯용
@app.websocket("/ws/widget/{customer_external_id}")
async def widget_websocket(websocket: WebSocket, customer_external_id: str):
    """
    고객 위젯용 WebSocket
    - 상담원 답장 실시간 수신
    """
    await manager.connect(websocket, f"widget_{customer_external_id}")

    try:
        while True:
            # 위젯은 REST API로 메시지 보내므로 여기서는 수신만
            data = await websocket.receive_text()
            # 필요시 처리 (핑퐁 등)

    except WebSocketDisconnect:
        manager.disconnect(f"widget_{customer_external_id}")


# 상담원 답장 처리
async def handle_agent_reply(message_data: dict, agent_id: str):
    """
    상담원이 고객에게 답장
    1. DB에 메시지 저장
    2. 해당 고객의 위젯 WebSocket으로 전송
    """
    db = next(get_db())
    
    try:
        conversation_id = message_data.get("conversation_id")
        content = message_data.get("content")
        
        if not conversation_id or not content:
            return
        
        # 메시지 저장
        new_message = Message(
            conversation_id=int(conversation_id),
            sender_type="agent",
            sender_id=int(agent_id),
            content=content,
            channel="widget",
        )
        
        db.add(new_message)
        db.commit()
        db.refresh(new_message)
        
        # 대화방 정보 조회
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if conversation and conversation.customer_id:  # type: ignore[attr-defined]
            # Customer 조회
            customer = db.query(models.Customer).filter(
                models.Customer.id == conversation.customer_id  # type: ignore[attr-defined]
            ).first()
            
            if customer:
                # 해당 고객의 위젯 WebSocket으로 전송
                widget_client_id = f"widget_{customer.external_id}"  # type: ignore[attr-defined]
                await manager.send_personal_message(
                    json.dumps({
                        "type": "agent_reply",
                        "message": {
                            "id": new_message.id,  # type: ignore[attr-defined]
                            "conversation_id": conversation_id,
                            "sender_type": "agent",
                            "content": content,
                            "created_at": new_message.created_at.isoformat()  # type: ignore[attr-defined]
                        }
                    }),
                    widget_client_id
                )
        
        # 다른 상담원들에게도 알림 (옵션)
        await manager.broadcast_to_agents(json.dumps({
            "type": "conversation_updated",
            "conversation_id": conversation_id
        }))
        
    except Exception as e:
        print(f"Error handling agent reply: {e}")
    finally:
        db.close()


# 메시지 저장 + AI 응답
async def process_message(message_data: dict, client_id: str):
    """메시지 DB 저장 + 필요시 봇 응답"""
    db = next(get_db())

    try:
        content: str = (message_data.get("content") or "").strip()
        if not content:
            return

        conversation_id = message_data.get("conversation_id")

        # 대화 ID 없으면 새로 생성
        if conversation_id is None:
            conv = Conversation(
                customer_id=client_id,
                channel_type=message_data.get("channel", "web"),
                status="open",
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)
            conversation_id = conv.id
        else:
            conversation_id = int(conversation_id)

        sender_type = message_data.get("sender_type", "customer")
        channel = message_data.get("channel", "web")

        new_message = Message(
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_id=None,  # WebSocket에서는 문자열 client_id라 None 처리
            content=content,
            channel=channel,
        )

        db.add(new_message)
        db.commit()
        db.refresh(new_message)

        # AI 챗봇 자동 응답 (옵션)
        if message_data.get("enable_bot"):
            bot_response = await get_bot_response(content)

            bot_message = Message(
                conversation_id=conversation_id,
                sender_type="bot",
                sender_id=None,
                content=bot_response,
                channel=channel,
            )
            db.add(bot_message)
            db.commit()
            db.refresh(bot_message)

            # datetime 인스턴스인지 확인 후 timestamp 생성 (Pylance 에러 방지)
            created = bot_message.created_at
            bot_ts = created.isoformat() if isinstance(created, datetime) else None

            await manager.send_personal_message(
                json.dumps(
                    {
                        "type": "bot_response",
                        "message": {
                            "conversation_id": conversation_id,
                            "sender_type": "bot",
                            "content": bot_response,
                            "channel": channel,
                            "timestamp": bot_ts,
                        },
                    }
                ),
                client_id,
            )

    except Exception as e:
        print(f"Error processing message: {e}")
    finally:
        db.close()


async def get_bot_response(message: str) -> str:
    """AI 챗봇 응답 생성 (services.chatbot.generate_response 사용)"""
    try:
        from .services.chatbot import generate_response

        response = await generate_response(message)
        return response
    except Exception:
        return "죄송합니다. 잠시 후 다시 시도해주세요."


# 메시지 전송 API (REST)
@app.post("/api/messages/send")
async def send_message(message: MessageCreate, db: Session = Depends(get_db)):
    """REST API로 메시지 전송 (모든 채널 통합)"""
    try:
        new_message = Message(
            conversation_id=message.conversation_id,
            sender_type=message.sender_type,
            sender_id=message.sender_id,
            content=message.content,
            channel=message.channel,
        )

        db.add(new_message)
        db.commit()
        db.refresh(new_message)

        created = new_message.created_at
        ts = created.isoformat() if isinstance(created, datetime) else None

        # WebSocket으로도 뿌려주기
        await manager.broadcast(
            json.dumps(
                {
                    "type": "new_message",
                    "message": {
                        "id": new_message.id,
                        "conversation_id": new_message.conversation_id,
                        "sender_type": new_message.sender_type,
                        "content": new_message.content,
                        "channel": new_message.channel,
                        "timestamp": ts,
                    },
                }
            )
        )

        return {"status": "success", "message_id": new_message.id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 대화 내역 조회
@app.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: int, db: Session = Depends(get_db)
):
    """대화 내역 조회"""
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )

    result = []
    for msg in messages:
        created = msg.created_at
        ts = created.isoformat() if isinstance(created, datetime) else None

        result.append(
            {
                "id": msg.id,
                "sender_type": msg.sender_type,
                "content": msg.content,
                "channel": msg.channel,
                "timestamp": ts,
            }
        )

    return {
        "conversation_id": conversation_id,
        "messages": result,
    }


# 채널 연동
@app.post("/api/channels/connect")
async def connect_channel(channel: ChannelConnect, db: Session = Depends(get_db)):
    """외부 채널 연동"""
    try:
        new_channel = Channel(
            type=channel.channel_type,
            name=channel.name,
            config_json=json.dumps(channel.credentials),
            is_active=True,
        )

        db.add(new_channel)
        db.commit()
        db.refresh(new_channel)

        return {"status": "success", "channel": channel.channel_type}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
