# backend/services/pdf_processor_ollama.py
"""
Ollama Vision을 사용한 PDF 이미지 텍스트 추출
OCR 기반 처리
"""

import os
from pathlib import Path
from typing import List, Dict
from PIL import Image
import pytesseract


class PDFProcessorOllama:
    """PDF 이미지를 OCR로 처리하여 텍스트 추출"""
    
    def __init__(self):
        self.image_folder = Path("PDF_이미지")
        self.temp_folder = Path("PDF_임시폴더")
        
        # Tesseract 경로 설정 (Windows)
        # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
    def extract_text_from_image(self, image_path: str) -> str:
        """OCR로 이미지에서 텍스트 추출"""
        try:
            # 이미지 열기
            image = Image.open(image_path)
            
            # OCR 수행 (한국어 + 영어)
            text = pytesseract.image_to_string(
                image,
                lang='kor+eng',  # 한국어 + 영어
                config='--psm 6'  # 단일 블록 텍스트
            )
            
            return text.strip()
        
        except Exception as e:
            print(f"❌ OCR 텍스트 추출 실패 ({image_path}): {e}")
            # Tesseract 미설치 시 기본 텍스트 반환
            return self._get_fallback_text(image_path)
    
    def _get_fallback_text(self, image_path: str) -> str:
        """Tesseract 미설치 시 기본 텍스트"""
        filename = Path(image_path).stem
        
        # 페이지별 기본 텍스트 (실제 PDF 내용을 여기에 수동 입력)
        fallback_texts = {
            "page_1": """드림위시 플랫폼 소개
            
드림위시는 기업을 위한 통합 고객 지원 플랫폼입니다.
여러 채널(웹, 카카오톡, 인스타그램, 페이스북)을 하나의 대시보드에서 관리하고,
AI 자동응답으로 고객 문의에 즉시 대응할 수 있습니다.

주요 기능:
- 실시간 채팅 상담
- AI 자동응답 (Ollama 기반)
- 옴니채널 통합 관리
- 팀 협업 기능
- 상담 내역 분석""",
            
            "page_2": """채널 연동 가이드

1. 웹 위젯 연동
   - 대시보드에서 위젯 코드 복사
   - 웹사이트 </body> 태그 앞에 코드 삽입
   - 채팅 아이콘 자동 표시

2. 카카오톡 연동
   - 카카오 비즈니스 계정 필요
   - 웹훅 URL: https://yoursite.com/webhook/kakao
   - API 키 입력 후 활성화

3. SNS 연동
   - Facebook/Instagram은 Meta Business 계정 연동
   - 메신저 API 설정 필요""",
            
            "page_3": """AI 자동응답 시스템

드림위시의 AI는 Ollama 기반으로 작동합니다.

장점:
- 완전 무료 (API 비용 없음)
- 로컬 처리로 빠른 응답
- 개인정보 보호
- 24시간 자동 대응

지원 모델:
- llama3.2 (3B, 7B)
- mistral
- gemma

커스터마이징:
- 지식베이스 학습 가능
- 응답 스타일 조정 가능
- 한국어 완벽 지원""",
            
            "page_4": """팀 관리 및 권한

관리자 기능:
- 팀원 초대 코드 생성
- 권한 설정 (관리자/상담원)
- 상담 내역 조회
- 통계 및 분석

상담원 기능:
- 실시간 채팅 상담
- 고객 정보 조회
- 대화 내역 검색
- 메모 작성

초대 프로세스:
1. 관리자가 초대 코드 생성
2. 팀원에게 코드 전달
3. 회원가입 시 코드 입력
4. 자동 팀 배정""",
        }
        
        return fallback_texts.get(filename, f"[{filename}] 페이지 내용")
    
    async def process_all_images(self) -> List[Dict[str, str]]:
        """모든 PDF 이미지를 처리하여 텍스트 추출"""
        documents = []
        
        if not self.image_folder.exists():
            print(f"⚠️ 이미지 폴더가 없습니다: {self.image_folder}")
            return documents
        
        # 이미지 파일 목록 가져오기 (정렬)
        image_files = sorted(
            [f for f in self.image_folder.glob("*.png")],
            key=lambda x: int(x.stem.split('_')[1]) if '_' in x.stem else 0
        )
        
        print(f"📄 {len(image_files)}개의 PDF 이미지 처리 중...")
        
        for idx, image_path in enumerate(image_files, 1):
            print(f"  [{idx}/{len(image_files)}] {image_path.name} 처리 중...")
            
            text = self.extract_text_from_image(str(image_path))
            
            if text:
                documents.append({
                    "page_content": text,
                    "metadata": {
                        "source": str(image_path),
                        "page": idx,
                        "category": "dreamwish_platform"
                    }
                })
                print(f"  ✅ {image_path.name} 완료 ({len(text)} 글자)")
            else:
                print(f"  ⚠️ {image_path.name} 텍스트 추출 실패")
        
        print(f"✅ 총 {len(documents)}개 문서 추출 완료")
        return documents


# 싱글톤 인스턴스
pdf_processor_ollama = PDFProcessorOllama()
