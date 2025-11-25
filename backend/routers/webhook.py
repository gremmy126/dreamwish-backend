from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import json

from .. import models
from ..auth_utils import get_db
from ..websocket import manager
from ..services.kakao_service import process_kakao_message, send_kakao_message, setup_kakao_webhook
from ..services.instagram_service import send_instagram_message, setup_instagram_webhook
from ..services.facebook_service import send_facebook_message, setup_facebook_webhook
from ..services.ollama_chatbot import ollama_chatbot
from ..services.ollama_knowledge_base import ollama_knowledge_base
from ..services.agent_assignment import AgentAssignmentService
from ..services.business_hours import BusinessHoursService

router = APIRouter(prefix="/webhook", tags=["Webhooks"])


async def process_incoming_message(
    db: Session,
    platform: str,
    external_id: str,
    name: str,
    message: str,
    profile_image: str | None = None
):
    """
    모든 채널의 메시지를 통일된 형식으로 처리
    
    1. Customer 조회/생성
    2. Conversation 조회/생성
    3. Message 저장
    4. WebSocket으로 상담원에게 알림
    """
    
    # 1) Customer 찾기 또는 생성
    customer = db.query(models.Customer).filter(
        models.Customer.external_id == external_id,
        models.Customer.platform == platform
    ).first()
    
    if not customer:
        customer = models.Customer(
            external_id=external_id,
            platform=platform,
            name=name or f"{platform}_user",
            profile_image=profile_image
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        print(f"✅ 새 고객 생성: {customer.name} ({platform})")
    else:
        # 기존 고객 정보 업데이트 (이름이나 프로필 이미지 변경된 경우)
        updated = False
        if name and str(customer.name) != name:  # type: ignore[attr-defined]
            customer.name = name  # type: ignore[attr-defined]
            updated = True
        if profile_image and str(customer.profile_image or '') != profile_image:  # type: ignore[attr-defined]
            customer.profile_image = profile_image  # type: ignore[attr-defined]
            updated = True
        if updated:
            db.commit()
            db.refresh(customer)
            print(f"✅ 고객 정보 업데이트: {customer.name} ({platform})")
    
    # 2) Conversation 찾기 또는 생성
    conversation = db.query(models.Conversation).filter(
        models.Conversation.customer_id == customer.id,
        models.Conversation.channel_type == platform
    ).first()
    
    if not conversation:
        conversation = models.Conversation(
            customer_id=customer.id,
            channel_type=platform,
            profile_name=name,
            profile_image=profile_image,
            status="open"
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        print(f"✅ 새 대화방 생성: {conversation.id}")
        
        # 새 대화방에 상담원 자동 배정
        AgentAssignmentService.assign_agent_to_conversation(db, int(conversation.id))  # type: ignore
    else:
        # 대화방 프로필 정보 업데이트
        updated = False
        if name and str(conversation.profile_name or '') != name:  # type: ignore[attr-defined]
            conversation.profile_name = name  # type: ignore[attr-defined]
            updated = True
        if profile_image and str(conversation.profile_image or '') != profile_image:  # type: ignore[attr-defined]
            conversation.profile_image = profile_image  # type: ignore[attr-defined]
            updated = True
        if updated:
            db.commit()
            print(f"✅ 대화방 정보 업데이트: {conversation.id}")
    
    # 3) 메시지 저장
    msg = models.Message(
        conversation_id=conversation.id,
        sender_type="customer",
        sender_id=None,
        content=message,
        channel=platform,
        message_type="text",
        status="received"
    )
    db.add(msg)
    
    # 4) Conversation 업데이트
    conversation.last_message_at = datetime.utcnow()  # type: ignore
    conversation.unread_count = (conversation.unread_count or 0) + 1  # type: ignore
    
    db.commit()
    db.refresh(msg)
    
    # 5) AI 자동 응답 판단 (운영시간 + 상담원 가용성)
    ai_response = None
    should_auto_respond = BusinessHoursService.should_auto_respond(db)
    
    if should_auto_respond or ollama_chatbot.should_auto_respond(message):
        # 대화 히스토리 조회
        history = db.query(models.Message).filter(
            models.Message.conversation_id == conversation.id  # type: ignore[attr-defined]
        ).order_by(models.Message.created_at.desc()).limit(10).all()
        
        history_list = [{
            "sender_type": h.sender_type,  # type: ignore[attr-defined]
            "content": h.content  # type: ignore[attr-defined]
        } for h in reversed(history)]
        
        # RAG: 지식베이스에서 관련 정보 검색
        context = ollama_knowledge_base.get_context_for_query(message)
        
        # AI 응답 생성
        ai_response = await ollama_chatbot.get_response(
            message,
            conversation_history=history_list,
            context=context
        )
        
        # AI 응답 저장
        if ai_response:
            ai_msg = models.Message(  # type: ignore[call-arg]
                conversation_id=conversation.id,  # type: ignore[attr-defined]
                sender_type="bot",
                sender_id=None,
                content=ai_response,
                channel=platform
            )
            db.add(ai_msg)
            db.commit()
            db.refresh(ai_msg)
            
            print(f"🤖 AI 자동 응답: {ai_response[:50]}...")
    
    # 6) WebSocket으로 상담원에게 실시간 알림
    import json
    await manager.broadcast_to_agents(json.dumps({  # type: ignore[arg-type]
        "type": "new_customer_message",
        "conversation_id": int(conversation.id),  # type: ignore[arg-type]
        "customer_id": int(customer.id),  # type: ignore[arg-type]
        "customer_name": str(customer.name),  # type: ignore[arg-type]
        "profile_image": str(customer.profile_image) if customer.profile_image else None,  # type: ignore[attr-defined]
        "channel": platform,
        "message": {
            "id": int(msg.id),  # type: ignore[arg-type]
            "content": message,
            "created_at": msg.created_at.isoformat()  # type: ignore[attr-defined]
        },
        "ai_responded": ai_response is not None
    }))
    
    print(f"✅ {platform} 메시지 처리 완료: {message[:50]}...")
    
    return {
        "status": "success", 
        "conversation_id": int(conversation.id),  # type: ignore[arg-type]
        "ai_responded": ai_response is not None
    }


@router.get("/kakao")
async def kakao_webhook_verify():
    """카카오톡 스킬 서버 검증 전용 엔드포인트"""
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": "스킬 서버가 정상 작동 중입니다."
                    }
                }
            ]
        }
    }


@router.post("/kakao")
async def kakao_webhook(request: Request, db: Session = Depends(get_db)):
    """카카오톡 웹훅 수신 - DB 저장 + Ollama AI 자동응답"""
    
    # POST 요청 (실제 메시지 처리)
    payload = await request.json()
    print(f"📨 카카오 웹훅 수신 (전체): {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    # 상담 종료 이벤트 처리
    event_type = payload.get("event", {}).get("type") or payload.get("type")
    if event_type == "leave" or event_type == "end_chat":
        user_id = (
            payload.get("user_key") or
            payload.get("userRequest", {}).get("user", {}).get("id") or
            payload.get("event", {}).get("user", {}).get("id") or
            ""
        )
        
        if user_id:
            print(f"🔚 카카오톡 상담 종료 이벤트 - user_id: {user_id}")
            
            # 해당 고객의 대화방 종료 처리
            conversation = db.query(models.Conversation).join(models.Customer).filter(
                models.Customer.external_id == user_id,
                models.Customer.platform == "kakao",
                models.Conversation.status == "open"
            ).first()
            
            if conversation:
                conversation.status = "closed"  # type: ignore[attr-defined]
                db.commit()
                print(f"✅ 대화방 {conversation.id} 종료 처리 완료")  # type: ignore[attr-defined]
                
                # WebSocket으로 상담원에게 알림
                await manager.broadcast_to_agents(json.dumps({
                    "type": "conversation_ended",
                    "conversation_id": int(conversation.id),  # type: ignore[arg-type,attr-defined]
                    "reason": "customer_left",
                    "message": "고객이 상담을 종료했습니다."
                }))
        
        return {"status": "ok", "message": "Conversation ended"}
    
    # 여러 카카오톡 포맷 처리
    user_message = (
        payload.get("content") or 
        payload.get("userRequest", {}).get("utterance") or
        payload.get("message", {}).get("text") or
        ""
    )
    
    user_id = (
        payload.get("user_key") or
        payload.get("userRequest", {}).get("user", {}).get("id") or
        payload.get("sender", {}).get("id") or
        ""
    )
    
    user_name = (
        payload.get("user_name") or
        payload.get("userRequest", {}).get("user", {}).get("properties", {}).get("nickname") or
        payload.get("userRequest", {}).get("user", {}).get("properties", {}).get("plusfriend_user_key") or
        "Kakao User"
    )
    
    # 프로필 이미지 추출
    profile_image = (
        payload.get("userRequest", {}).get("user", {}).get("properties", {}).get("profileImageUrl") or
        None
    )
    
    print(f"🔍 추출된 데이터 - user_id: {user_id}, user_name: {user_name}, message: {user_message}")
    
    if user_id and user_message:
        # DB에 저장 (프로필 이미지 포함)
        await process_incoming_message(
            db=db,
            platform="kakao",
            external_id=user_id,
            name=user_name,
            message=user_message,
            profile_image=profile_image
        )
        print(f"✅ DB 저장 완료")
    else:
        print(f"⚠️ 필수 데이터 누락 - user_id: {bool(user_id)}, message: {bool(user_message)}")
    
    # 메시지 처리 및 AI 응답
    response = await process_kakao_message(payload)
    return response


@router.post("/instagram")
async def instagram_webhook(request: Request, db: Session = Depends(get_db)):
    """인스타그램 웹훅 수신 - Ollama AI 자동응답"""
    from ..services.instagram_service import get_instagram_user_profile
    
    payload = await request.json()
    print(f"📨 인스타그램 웹훅 수신: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    # Meta Instagram 메시지 포맷 처리
    entry = payload.get("entry", [])
    if not entry:
        print("⚠️ entry가 없는 페이로드")
        return {"status": "ok"}
    
    for item in entry:
        messaging = item.get("messaging", [])
        for msg_event in messaging:
            sender_id = msg_event.get("sender", {}).get("id")
            message_data = msg_event.get("message", {})
            message_text = message_data.get("text", "")
            
            if sender_id and message_text:
                print(f"🔍 인스타그램 메시지 - sender: {sender_id}, text: {message_text}")
                
                # 프로필 정보 조회
                profile = await get_instagram_user_profile(sender_id, db)
                user_name = profile.get("name", "Instagram User")
                profile_pic = profile.get("profile_pic")
                
                print(f"👤 인스타그램 프로필: {user_name}, 사진: {profile_pic}")
                
                # 통합 처리
                result = await process_incoming_message(
                    db=db,
                    platform="instagram",
                    external_id=sender_id,
                    name=user_name,
                    message=message_text,
                    profile_image=profile_pic
                )
                print(f"✅ 인스타그램 메시지 처리 완료: {result}")
    
    return {"status": "ok"}


@router.get("/instagram")
async def instagram_webhook_verify(request: Request):
    """인스타그램 웹훅 검증"""
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    expected_token = "dreamwish_verify_token"
    
    if verify_token == expected_token and challenge:
        return {"challenge": int(challenge)}
    return {"error": "Invalid verify token"}


@router.post("/facebook")
async def facebook_webhook(request: Request, db: Session = Depends(get_db)):
    """페이스북 Messenger 웹훅 수신 - Ollama AI 자동응답"""
    from ..services.facebook_service import get_facebook_user_profile
    
    payload = await request.json()
    print(f"📨 페이스북 웹훅 수신: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    # Meta Messenger 메시지 포맷 처리
    entry = payload.get("entry", [])
    if not entry:
        print("⚠️ entry가 없는 페이로드")
        return {"status": "ok"}
    
    for item in entry:
        messaging = item.get("messaging", [])
        for msg_event in messaging:
            sender_id = msg_event.get("sender", {}).get("id")
            message_data = msg_event.get("message", {})
            message_text = message_data.get("text", "")
            
            if sender_id and message_text:
                print(f"🔍 페이스북 메시지 - sender: {sender_id}, text: {message_text}")
                
                # 프로필 정보 조회
                profile = await get_facebook_user_profile(sender_id, db)
                user_name = profile.get("name", "Facebook User")
                profile_pic = profile.get("profile_pic")
                
                print(f"👤 페이스북 프로필: {user_name}, 사진: {profile_pic}")
                
                # 통합 처리
                result = await process_incoming_message(
                    db=db,
                    platform="facebook",
                    external_id=sender_id,
                    name=user_name,
                    message=message_text,
                    profile_image=profile_pic
                )
                print(f"✅ 페이스북 메시지 처리 완료: {result}")
    
    return {"status": "ok"}


@router.get("/facebook")
async def facebook_webhook_verify(request: Request):
    """페이스북 웹훅 검증"""
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    expected_token = "dreamwish_verify_token"
    
    if verify_token == expected_token and challenge:
        return {"challenge": int(challenge)}
    return {"error": "Invalid verify token"}


@router.post("/email")
async def email_webhook(request: Request, db: Session = Depends(get_db)):
    """이메일 웹훅 수신 - SMTP/IMAP 연동"""
    payload = await request.json()
    print(f"📨 이메일 웹훅 수신: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    # 이메일 포맷 처리
    sender_email = payload.get("from", "")
    sender_name = payload.get("from_name", payload.get("from", "").split("@")[0])
    subject = payload.get("subject", "제목 없음")
    body = payload.get("body", payload.get("text", payload.get("html", "")))
    
    if sender_email and body:
        print(f"🔍 이메일 메시지 - sender: {sender_email}, subject: {subject}")
        
        # 메시지 내용 (제목 포함)
        message_content = f"[{subject}]\n\n{body}"
        
        # 통합 처리
        result = await process_incoming_message(
            db=db,
            platform="email",
            external_id=sender_email,
            name=sender_name,
            message=message_content,
            profile_image=None
        )
        print(f"✅ 이메일 메시지 처리 완료: {result}")
    
    return {"status": "ok"}


@router.get("/email")
async def email_webhook_verify(request: Request):
    """이메일 웹훅 검증"""
    return {"status": "ok", "message": "Email webhook is ready"}
