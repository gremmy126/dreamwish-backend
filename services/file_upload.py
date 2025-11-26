# backend/services/file_upload.py
"""
파일 업로드 서비스
- 이미지/파일 업로드
- 클라우드 스토리지 연동 (Google Cloud Storage)
- 파일 타입 검증
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from .. import models


class FileUploadService:
    """파일 업로드 관리"""
    
    # 허용된 파일 타입
    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    ALLOWED_FILE_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "text/csv"
    }
    ALLOWED_VIDEO_TYPES = {"video/mp4", "video/mpeg", "video/quicktime"}
    
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    
    def __init__(self, upload_dir: str = "uploads"):
        """
        Args:
            upload_dir: 로컬 업로드 디렉토리 경로
        """
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_file(self, file: UploadFile) -> bool:
        """
        파일 검증
        - 파일 타입
        - 파일 크기
        """
        content_type = file.content_type
        
        # 파일 타입 검증
        all_allowed = (
            self.ALLOWED_IMAGE_TYPES | 
            self.ALLOWED_FILE_TYPES | 
            self.ALLOWED_VIDEO_TYPES
        )
        
        if content_type not in all_allowed:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 파일 타입입니다: {content_type}"
            )
        
        # 파일 크기 검증 (실제 읽어서 확인)
        file.file.seek(0, 2)  # 파일 끝으로 이동
        file_size = file.file.tell()
        file.file.seek(0)  # 다시 처음으로
        
        max_size = self.MAX_FILE_SIZE
        if content_type in self.ALLOWED_IMAGE_TYPES:
            max_size = self.MAX_IMAGE_SIZE
        
        if file_size > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"파일 크기가 너무 큽니다. 최대 {max_size / 1024 / 1024}MB"
            )
        
        return True
    
    async def save_file(
        self,
        file: UploadFile,
        db: Session,
        message_id: Optional[int] = None,
        uploaded_by_type: str = "customer",
        uploaded_by_id: Optional[str] = None
    ) -> models.FileUpload:
        """
        파일 저장 (로컬 또는 클라우드)
        
        Args:
            file: 업로드된 파일
            db: DB 세션
            message_id: 연결할 메시지 ID
            uploaded_by_type: customer/agent
            uploaded_by_id: 업로더 ID
        
        Returns:
            FileUpload: 저장된 파일 정보
        """
        # 파일 검증
        self.validate_file(file)
        
        # 고유 파일명 생성
        file_ext = Path(file.filename or "file").suffix  # type: ignore
        stored_filename = f"{uuid.uuid4()}{file_ext}"
        
        # 날짜별 디렉토리 생성
        today = datetime.now().strftime("%Y%m%d")
        date_dir = self.upload_dir / today
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일 저장
        file_path = date_dir / stored_filename
        
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # 파일 크기
        file_size = len(contents)
        
        # 공개 URL 생성 (로컬 환경)
        file_url = f"/uploads/{today}/{stored_filename}"
        
        # DB에 저장
        file_upload = models.FileUpload(
            message_id=message_id,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=str(file_path),
            file_url=file_url,
            file_type=file.content_type,
            file_size=file_size,
            uploaded_by_type=uploaded_by_type,
            uploaded_by_id=uploaded_by_id
        )
        
        db.add(file_upload)
        db.commit()
        db.refresh(file_upload)
        
        print(f"✅ 파일 업로드 완료: {file.filename} → {stored_filename}")
        
        return file_upload
    
    def get_file_url(self, file_upload: models.FileUpload) -> str:
        """
        파일 공개 URL 조회
        """
        return str(file_upload.file_url or "")  # type: ignore
    
    def delete_file(self, db: Session, file_id: int) -> bool:
        """
        파일 삭제 (물리적 삭제 + DB)
        """
        file_upload = db.query(models.FileUpload).filter(
            models.FileUpload.id == file_id
        ).first()
        
        if not file_upload:
            return False
        
        # 물리적 파일 삭제
        file_path = Path(str(file_upload.file_path))  # type: ignore
        if file_path.exists():
            file_path.unlink()
        
        # DB에서 삭제
        db.delete(file_upload)
        db.commit()
        
        print(f"✅ 파일 삭제 완료: {file_upload.original_filename}")
        
        return True


# 전역 인스턴스
file_upload_service = FileUploadService()
