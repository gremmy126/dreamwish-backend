"""
카카오 비즈니스 메시지 서비스 (Ollama 연동)
대시보드에서 설정한 API 키 사용
"""

import aiohttp
import os
import json
from sqlalchemy.orm import Session
from backend.services.ollama_chatbot import ollama_chatbot
from backend.services.ollama_knowledge_base import ollama_knowledge_base
from backend import models


def get_kakao_credentials(db: Session) -> dict:
    """데이터베이스에서 카카오 채널 정보 조회"""
    channel = db.query(models.Channel).filter(
        models.Channel.type == "kakao",
        models.Channel.is_active == True
    ).first()
    
    if channel and channel.config_json:  # type: ignore[attr-defined]
        try:
            return json.loads(channel.config_json)  # type: ignore[arg-type]
        except:
            pass
    
    # 폴백: 환경변수에서 읽기 (하위 호환성)
    return {
        "api_key": os.getenv("KAKAO_RESTAPI_KEY", ""),
        "sender_key": os.getenv("KAKAO_SENDER_KEY", ""),
        "channel_id": os.getenv("KAKAO_CHANNEL_ID", "")
    }


async def process_kakao_message(message_data: dict) -> dict:
    """카카오톡 메시지 처리 및 AI 응답"""
    
    try:
        # 여러 카카오톡 포맷 처리
        user_message = (
            message_data.get("content") or 
            message_data.get("userRequest", {}).get("utterance") or
            ""
        )
        
        user_id = (
            message_data.get("user_key") or
            message_data.get("userRequest", {}).get("user", {}).get("id") or
            ""
        )
        
        if not user_message:
            # 메시지가 없으면 기본 응답
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": "안녕하세요! 무엇을 도와드릴까요?"
                            }
                        }
                    ]
                }
            }
        
        # AI 자동응답 판단
        if ollama_chatbot.should_auto_respond(user_message):
            # 지식베이스 검색
            context = ollama_knowledge_base.get_context_for_query(user_message)
            
            # AI 응답 생성
            ai_response = await ollama_chatbot.get_response(
                user_message,
                context=context
            )
            
            # 카카오톡 응답 포맷
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": ai_response or "답변을 생성할 수 없습니다."
                            }
                        }
                    ],
                    "quickReplies": [
                        {
                            "label": "상담원 연결",
                            "action": "message",
                            "messageText": "상담원과 대화하고 싶어요"
                        }
                    ]
                }
            }
        
        # 상담원 연결 필요
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": "안녕하세요, 문의 주셔서 감사합니다.\n상담원이 곧 연락드릴 예정이니 잠시만 기다려 주시기 바랍니다. 😊"
                        }
                    }
                ]
            }
        }
    
    except Exception as e:
        print(f"❌ 카카오 메시지 처리 오류: {e}")
        # 에러 발생 시에도 카카오톡 포맷으로 응답
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
                        }
                    }
                ]
            }
        }


async def send_kakao_message(message: str, recipient_id: str, db: Session):
    """
    카카오톡 메시지 전송 (비즈니스 메시지 API 사용)
    대시보드에서 설정한 API 키 사용
    """
    
    credentials = get_kakao_credentials(db)
    api_key = credentials.get("api_key", "")
    
    if not api_key:
        print("⚠️ KAKAO_API_KEY가 설정되지 않았습니다.")
        print("대시보드 > 채널 연동에서 카카오 API 키를 입력하세요.")
        return {"status": "error", "message": "API key not configured"}
    
    # 방법 1: 알림톡 API (비즈니스 계정 필요)
    url = f"https://kapi.kakao.com/v1/api/talk/friends/message/default/send"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    template_object = {
        "object_type": "text",
        "text": message,
        "link": {
            "web_url": "https://dreamwish.com",
            "mobile_web_url": "https://dreamwish.com"
        },
        "button_title": "확인"
    }
    
    data = {
        "receiver_uuids": json.dumps([recipient_id]),
        "template_object": json.dumps(template_object)
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as response:
                result = await response.json()
                print(f"📤 카카오톡 메시지 전송 결과: {result}")
                return result
    except Exception as e:
        print(f"❌ 카카오톡 메시지 전송 실패: {e}")
        return {"status": "error", "message": str(e)}


async def setup_kakao_webhook(credentials: dict):
    """카카오톡 웹훅 설정"""
    
    # 웹훅 URL
    webhook_url = credentials.get("webhook_url", "https://your-domain.com/webhook/kakao")
    
    return {
        "webhook_url": webhook_url,
        "status": "configured",
        "instructions": [
            "1. 카카오 디벨로퍼스(https://developers.kakao.com) 접속",
            "2. 내 애플리케이션 > 카카오톡 채널 선택",
            f"3. 봇 > 시나리오 봇 > 웹훅 URL 등록: {webhook_url}",
            "4. 테스트 메시지 전송하여 확인"
        ]
    }
