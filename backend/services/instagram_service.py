# backend/services/instagram_service.py
"""
인스타그램 DM 서비스 (Ollama 연동)
대시보드에서 설정한 액세스 토큰 사용
"""

import aiohttp
import os
import json
from sqlalchemy.orm import Session
from backend import models


def get_instagram_credentials(db: Session) -> dict:
    """데이터베이스에서 인스타그램 채널 정보 조회"""
    channel = db.query(models.Channel).filter(
        models.Channel.type == "instagram",
        models.Channel.is_active == True
    ).first()
    
    if channel and channel.config_json:  # type: ignore[attr-defined]
        try:
            return json.loads(channel.config_json)  # type: ignore[arg-type]
        except:
            pass
    
    # 폴백: 환경변수에서 읽기 (페이스북 토큰 공유)
    return {
        "access_token": os.getenv("INSTAGRAM_ACCESS_TOKEN") or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    }


async def get_instagram_user_profile(user_id: str, db: Session):
    """인스타그램 사용자 프로필 정보 조회"""
    credentials = get_instagram_credentials(db)
    access_token = credentials.get("access_token", "")
    
    if not access_token:
        print("⚠️ INSTAGRAM_ACCESS_TOKEN이 설정되지 않았습니다")
        print("대시보드 > 채널 연동에서 인스타그램 액세스 토큰을 입력하세요.")
        return {"name": "Instagram User", "profile_pic": None}
    
    url = f"https://graph.facebook.com/v18.0/{user_id}"
    params = {
        "fields": "name,profile_picture_url",
        "access_token": access_token
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "name": data.get("name", "Instagram User"),
                        "profile_pic": data.get("profile_pic")
                    }
                else:
                    print(f"❌ 인스타그램 프로필 조회 실패: {response.status}")
                    return {"name": "Instagram User", "profile_pic": None}
    except Exception as e:
        print(f"❌ 인스타그램 프로필 조회 오류: {e}")
        return {"name": "Instagram User", "profile_pic": None}


async def send_instagram_message(message: str, recipient_id: str, db: Session):
    """인스타그램 DM 전송"""
    
    credentials = get_instagram_credentials(db)
    access_token = credentials.get("access_token", "")
    
    if not access_token:
        print("⚠️ INSTAGRAM_ACCESS_TOKEN이 설정되지 않았습니다")
        print("대시보드 > 채널 연동에서 인스타그램 액세스 토큰을 입력하세요.")
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


async def setup_instagram_webhook(credentials: dict):
    """인스타그램 웹훅 설정"""
    
    webhook_url = credentials.get("webhook_url", "https://your-domain.com/webhook/instagram")
    
    return {
        "webhook_url": webhook_url,
        "status": "configured",
        "instructions": [
            "1. Meta for Developers 접속",
            "2. Instagram Messaging 연결",
            f"3. 웹훅 URL: {webhook_url}",
            "4. 인스타그램 계정 구독 설정"
        ]
    }
