# backend/services/pdf_processor.py
"""
PDF를 이미지로 변환하고 GPT Vision으로 텍스트 추출
"""

import os
import base64
from pathlib import Path
from typing import List, Dict
from openai import AsyncOpenAI
from PIL import Image
import fitz  # PyMuPDF

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


async def process_pdf_and_save_to_vectordb(pdf_path: str) -> bool:
    """
    PDF 파일을 처리하여 벡터 DB에 저장
    """
    try:
        from langchain_community.document_loaders import PyMuPDFLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_community.embeddings import OpenAIEmbeddings
        from langchain_community.vectorstores import FAISS
        
        # PDF 로드
        loader = PyMuPDFLoader(pdf_path)
        documents = loader.load()
        
        if not documents:
            print(f"⚠️ {pdf_path}에서 문서를 추출할 수 없습니다")
            return False
        
        # 청크 분할
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
        )
        chunks = text_splitter.split_documents(documents)
        
        if not chunks:
            print(f"⚠️ {pdf_path}에서 청크를 생성할 수 없습니다")
            return False
        
        # 벡터 DB에 저장
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        faiss_path = "faiss_index"
        
        if os.path.exists(faiss_path):
            # 기존 인덱스에 추가
            vector_store = FAISS.load_local(faiss_path, embeddings, allow_dangerous_deserialization=True)
            vector_store.add_documents(chunks)
        else:
            # 새 인덱스 생성
            vector_store = FAISS.from_documents(chunks, embeddings)
        
        # 저장
        vector_store.save_local(faiss_path)
        print(f"✅ {pdf_path} 처리 완료: {len(chunks)}개 청크 저장")
        return True
    
    except Exception as e:
        print(f"❌ PDF 처리 실패 ({pdf_path}): {e}")
        return False


class PDFProcessor:
    """PDF 이미지를 GPT Vision으로 처리하여 텍스트 추출"""
    
    def __init__(self):
        self.image_folder = Path("PDF_이미지")
        self.temp_folder = Path("PDF_임시폴더")
    
    def encode_image(self, image_path: str) -> str:
        """이미지를 base64로 인코딩"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    async def extract_text_from_image(self, image_path: str) -> str:
        """GPT Vision API로 이미지에서 텍스트 추출"""
        try:
            base64_image = self.encode_image(image_path)
            
            response = await client.chat.completions.create(
                model="gpt-4o",  # GPT-4 Vision
                messages=[
                    {
                        "role": "system",
                        "content": """당신은 드림위시 플랫폼 문서를 분석하는 AI입니다. 
이미지의 모든 텍스트를 정확하게 추출하고, 
플랫폼 기능, 사용법, 서비스 설명 등을 구조화하여 반환하세요.

추출 형식:
- 제목/소제목은 명확하게 구분
- 주요 기능과 설명을 항목별로 정리
- 숫자, 통계, 날짜 등은 정확하게 기록
- 표나 다이어그램은 텍스트로 설명"""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "이 이미지의 모든 텍스트와 내용을 추출해주세요. 드림위시 플랫폼에 관한 정보입니다."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.2
            )
            
            return response.choices[0].message.content or ""
        
        except Exception as e:
            print(f"❌ 이미지 텍스트 추출 실패 ({image_path}): {e}")
            return ""
    
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
            
            text = await self.extract_text_from_image(str(image_path))
            
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
pdf_processor = PDFProcessor()
