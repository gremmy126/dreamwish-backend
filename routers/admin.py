# backend/routers/admin.py
"""
관리자 전용 API
지식베이스 재구축 등
"""

from fastapi import APIRouter, Depends
from backend.auth_utils import get_current_admin
from backend.services.ollama_knowledge_base import ollama_knowledge_base

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/rebuild-knowledge-base")
async def rebuild_knowledge_base(current_user=Depends(get_current_admin)):
    """
    PDF 이미지에서 텍스트를 추출하여 지식베이스 재구축
    관리자만 사용 가능
    """
    await ollama_knowledge_base.rebuild_from_pdf()
    
    return {
        "success": True,
        "message": "Ollama 지식베이스 재구축 완료"
    }
