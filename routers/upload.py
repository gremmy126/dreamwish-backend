# backend/routers/upload.py
"""
파일 업로드 API
- 이미지/파일 업로드
- 메시지에 첨부
"""

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from typing import Optional
import json

from .. import models
from ..auth_utils import get_db, get_current_user
from ..services.file_upload import file_upload_service
from ..websocket import manager

router = APIRouter(prefix="/api/upload", tags=["Upload"])


@router.post("/file")
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    파일 업로드
    
    Args:
        file: 업로드할 파일
        conversation_id: 대화방 ID (선택)
    
    Returns:
        업로드된 파일 정보
    """
    try:
        # 파일 저장
        file_upload = await file_upload_service.save_file(
            file=file,
            db=db,
            message_id=None,  # 메시지 ID는 나중에 연결
            uploaded_by_type="agent",
            uploaded_by_id=str(current_user.id)
        )
        
        return {
            "success": True,
            "file_id": file_upload.id,
            "file_url": file_upload.file_url,
            "file_name": file_upload.original_filename,
            "file_type": file_upload.file_type,
            "file_size": file_upload.file_size
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 업로드 실패: {str(e)}")


@router.post("/message-with-file")
async def send_message_with_file(
    conversation_id: int = Form(...),
    content: str = Form(...),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    파일과 함께 메시지 전송
    
    Args:
        conversation_id: 대화방 ID
        content: 메시지 내용
        file: 첨부 파일 (선택)
    """
    # Conversation 조회
    conversation = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="대화방을 찾을 수 없습니다")
    
    # 파일 업로드 (있는 경우)
    file_upload = None
    message_type = "text"
    file_url = None
    
    if file:
        file_upload = await file_upload_service.save_file(
            file=file,
            db=db,
            uploaded_by_type="agent",
            uploaded_by_id=str(current_user.id)
        )
        
        # 메시지 타입 결정
        if file.content_type and file.content_type.startswith("image/"):
            message_type = "image"
        elif file.content_type and file.content_type.startswith("video/"):
            message_type = "video"
        else:
            message_type = "file"
        
        file_url = file_upload.file_url
    
    # 메시지 생성
    message = models.Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=current_user.id,
        content=content,
        channel=conversation.channel_type,
        message_type=message_type,
        file_url=file_url,
        file_type=file.content_type if file else None,
        file_size=file_upload.file_size if file_upload else None,
        status="sent"
    )
    
    db.add(message)
    
    # 파일 업로드와 메시지 연결
    if file_upload:
        file_upload.message_id = message.id
    
    db.commit()
    db.refresh(message)
    
    # Customer 정보 조회
    customer = db.query(models.Customer).filter(
        models.Customer.id == conversation.customer_id
    ).first()
    
    # 채널별 메시지 전송
    channel_type = str(conversation.channel_type)
    
    try:
        if channel_type == "kakao":
            from ..services.kakao_service import send_kakao_message
            await send_kakao_message(
                message=content,
                recipient_id=str(customer.external_id)  # type: ignore
            )
        elif channel_type == "instagram":
            from ..services.instagram_service import send_instagram_message
            await send_instagram_message(
                message=content,
                recipient_id=str(customer.external_id)  # type: ignore
            )
        elif channel_type == "facebook":
            from ..services.facebook_service import send_facebook_message
            await send_facebook_message(
                message=content,
                recipient_id=str(customer.external_id)  # type: ignore
            )
    except Exception as e:
        print(f"❌ 외부 채널 전송 실패: {e}")
        message.status = "failed"  # type: ignore
        db.commit()
    
    # WebSocket 알림
    await manager.broadcast_to_agents(json.dumps({
        "type": "agent_reply_sent",
        "conversation_id": conversation.id,
        "message": {
            "id": message.id,
            "content": content,
            "sender_type": "agent",
            "sender_name": current_user.name,
            "message_type": message_type,
            "file_url": file_url,
            "created_at": message.created_at.isoformat()
        }
    }))
    
    return {
        "success": True,
        "message_id": message.id,
        "file_url": file_url
    }


@router.delete("/file/{file_id}")
async def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """파일 삭제"""
    success = file_upload_service.delete_file(db, file_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    return {"success": True, "message": "파일이 삭제되었습니다"}
