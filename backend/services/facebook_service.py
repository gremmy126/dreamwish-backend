# backend/services/facebook_service.py
"""
페이스북 Messenger 서비스 (Ollama 연동)
대시보드에서 설정한 액세스 토큰 사용
"""

import aiohttp
import os
import json
from sqlalchemy.orm import Session
from backend import models


def get_facebook_credentials(db: Session) -> dict:
    """데이터베이스에서 페이스북 채널 정보 조회"""
    channel = db.query(models.Channel).filter(
        models.Channel.type == "facebook",
        models.Channel.is_active == True
    ).first()
    
    if channel and channel.config_json:  # type: ignore[attr-defined]
        try:
            return json.loads(channel.config_json)  # type: ignore[arg-type]
        except:
            pass
    
    # 폴백: 환경변수에서 읽기
    return {
        "page_access_token": os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", ""),
        "app_secret": os.getenv("FACEBOOK_APP_SECRET", ""),
        "page_id": os.getenv("FACEBOOK_PAGE_ID", "")
    }


async def get_facebook_user_profile(user_id: str, db: Session):
    """페이스북 사용자 프로필 정보 조회"""
    credentials = get_facebook_credentials(db)
    access_token = credentials.get("page_access_token", "")
    
    if not access_token:
        print("⚠️ FACEBOOK_PAGE_ACCESS_TOKEN이 설정되지 않았습니다")
        print("대시보드 > 채널 연동에서 페이스북 액세스 토큰을 입력하세요.")
        return {"name": "Facebook User", "profile_pic": None}
    
    url = f"https://graph.facebook.com/v18.0/{user_id}"
    params = {
        "fields": "name,profile_pic",
        "access_token": access_token
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "name": data.get("name", "Facebook User"),
                        "profile_pic": data.get("profile_pic")
                    }
                else:
                    print(f"❌ 페이스북 프로필 조회 실패: {response.status}")
                    return {"name": "Facebook User", "profile_pic": None}
    except Exception as e:
        print(f"❌ 페이스북 프로필 조회 오류: {e}")
        return {"name": "Facebook User", "profile_pic": None}


async def send_facebook_message(message: str, recipient_id: str, db: Session):
    """페이스북 메신저 메시지 전송"""
    
    credentials = get_facebook_credentials(db)
    access_token = credentials.get("page_access_token", "")
    
    if not access_token:
        print("⚠️ FACEBOOK_PAGE_ACCESS_TOKEN이 설정되지 않았습니다")
        print("대시보드 > 채널 연동에서 페이스북 액세스 토큰을 입력하세요.")
        return {"error": "Access token not configured"}
    
    url = "https://graph.facebook.com/v18.0/me/messages"
    
    params = {"access_token": access_token}
    
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message}
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params, json=data) as response:
            return await response.json()


async def setup_facebook_webhook(credentials: dict):
    """페이스북 웹훅 설정"""
    
    webhook_url = credentials.get("webhook_url", "https://your-domain.com/webhook/facebook")
    
    return {
        "webhook_url": webhook_url,
        "status": "configured",
        "instructions": [
            "1. Meta for Developers 접속",
            "2. Messenger 제품 추가",
            f"3. 웹훅 URL: {webhook_url}",
            "4. 페이지 구독 설정"
        ]
    }
