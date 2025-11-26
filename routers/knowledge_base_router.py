# backend/routers/knowledge_base.py
"""
지식베이스 관리 API
PDF 업로드 및 벡터 DB 관리
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os
import shutil
from datetime import datetime

from ..auth_utils import get_db, get_current_user
from ..services.pdf_processor import process_pdf_and_save_to_vectordb

router = APIRouter(prefix="/api/knowledge-base", tags=["Knowledge Base"])


@router.get("/stats")
async def get_kb_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    지식베이스 통계 조회
    """
    # FAISS 인덱스 확인
    faiss_path = "faiss_index"
    documents = 0
    chunks = 0
    last_updated = "없음"
    
    if os.path.exists(faiss_path):
        try:
            # 인덱스 파일들 확인
            index_file = os.path.join(faiss_path, "index.faiss")
            if os.path.exists(index_file):
                stat = os.stat(index_file)
                last_updated = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                
                # PDF 폴더의 파일 개수
                pdf_folder = "PDF_임시폴더"
                if os.path.exists(pdf_folder):
                    documents = len([f for f in os.listdir(pdf_folder) if f.endswith('.pdf')])
                
                # 대략적인 청크 수 (파일 크기 기반 추정)
                chunks = documents * 50  # 평균 50 청크/문서로 추정
        except Exception as e:
            print(f"통계 로드 오류: {e}")
    
    return {
        "documents": documents,
        "chunks": chunks,
        "last_updated": last_updated
    }


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    PDF 파일 업로드 및 처리
    업로드 후 자동으로 지식베이스 인덱스 재로드
    """
    if not file.filename or not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다")
    
    # 임시 폴더에 저장
    temp_dir = "PDF_임시폴더"
    os.makedirs(temp_dir, exist_ok=True)
    
    filename = file.filename or "uploaded.pdf"
    file_path = os.path.join(temp_dir, filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # PDF 처리 및 벡터 DB에 저장
        success = await process_pdf_and_save_to_vectordb(file_path)
        
        if success:
            # 지식베이스 인덱스 다시 로드
            from ..services.ollama_knowledge_base import ollama_knowledge_base
            ollama_knowledge_base.reload_index()
            print("✅ 지식베이스 인덱스 재로드 완료")
            
            return {
                "success": True,
                "message": f"{filename} 처리 완료 및 지식베이스 업데이트됨",
                "file_path": file_path
            }
        else:
            raise HTTPException(status_code=500, detail="PDF 처리 실패")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 오류: {str(e)}")


@router.delete("/document/{filename}")
async def delete_document(
    filename: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    문서 삭제 (벡터 DB 재구축 필요)
    """
    temp_dir = "PDF_임시폴더"
    file_path = os.path.join(temp_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    
    try:
        os.remove(file_path)
        return {"success": True, "message": f"{filename} 삭제 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"삭제 오류: {str(e)}")
