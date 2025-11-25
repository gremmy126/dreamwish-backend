# backend/services/knowledge_base.py
"""
드림위시 플랫폼 지식베이스
FAISS 벡터 DB를 활용한 RAG (Retrieval Augmented Generation)
PDF 이미지에서 추출한 플랫폼 정보 기반
"""

import os
from typing import List, Dict, Optional

try:
    from langchain_community.embeddings import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    LANGCHAIN_AVAILABLE = True
except ImportError:
    print("⚠️ LangChain 라이브러리가 설치되지 않았습니다. RAG 기능이 비활성화됩니다.")
    LANGCHAIN_AVAILABLE = False
    OpenAIEmbeddings = None  # type: ignore[misc,assignment]
    FAISS = None  # type: ignore[misc,assignment]
    Document = None  # type: ignore[misc,assignment]


class KnowledgeBase:
    """
    드림위시 지식베이스
    - PDF 이미지에서 추출한 플랫폼 정보
    - 드림위시 서비스 기능 및 사용법
    - 과거 상담 내역
    """
    
    def __init__(self):
        if not LANGCHAIN_AVAILABLE:
            self.vector_store = None
            self.index_path = "faiss_index"
            return
            
        self.embeddings = OpenAIEmbeddings()  # type: ignore[misc]
        self.vector_store = None
        self.index_path = "faiss_index"
        
    def load_or_create_index(self):
        """기존 인덱스 로드 또는 새로 생성"""
        
        if not LANGCHAIN_AVAILABLE:
            print("⚠️ LangChain이 설치되지 않아 지식베이스를 사용할 수 없습니다.")
            return
        
        if os.path.exists(self.index_path):
            # 기존 인덱스 로드
            self.vector_store = FAISS.load_local(  # type: ignore[misc]
                self.index_path, 
                self.embeddings,
                allow_dangerous_deserialization=True
            )
            print("✅ 기존 지식베이스 로드 완료")
        else:
            # 새 인덱스 생성
            self._create_initial_knowledge()
            print("✅ 새 지식베이스 생성 완료")
    
    def _create_initial_knowledge(self):
        """초기 지식베이스 구축 - PDF 이미지에서 텍스트 추출"""
        
        if not LANGCHAIN_AVAILABLE or not Document:
            return
        
        # PDF 이미지에서 추출한 텍스트로 지식베이스 구축
        print("📄 PDF 이미지에서 드림위시 플랫폼 정보 추출 중...")
        
        # 기본 플랫폼 정보 (PDF 처리 전 임시 데이터)
        documents = [
            Document(  # type: ignore[misc]
                page_content="""
                드림위시 플랫폼이란?
                
                드림위시는 옴니채널 고객 지원 플랫폼입니다.
                여러 채널(웹 위젯, 카카오톡, 인스타그램, 페이스북)을 통합 관리하고,
                AI 자동응답으로 고객 문의에 즉시 대응합니다.
                
                주요 기능:
                - 실시간 채팅 상담
                - AI 자동응답 (GPT-4 기반)
                - 다중 채널 통합 관리
                - 팀원 초대 및 권한 관리
                - 대화 내역 저장 및 검색
                """,
                metadata={"category": "platform_intro", "priority": "high"}
            ),
            Document(
                page_content="""
                드림위시 채널 연동 방법
                
                **웹 위젯:**
                - 자바스크립트 코드 복사하여 웹사이트에 삽입
                - 고객이 채팅 아이콘 클릭하여 즉시 상담 시작
                
                **카카오톡:**
                - 카카오 비즈니스 계정 필요
                - 웹훅 URL 등록하여 메시지 수신
                
                **인스타그램:**
                - Facebook Business 계정 연동
                - 인스타그램 DM 자동 수신
                
                **페이스북:**
                - Facebook Page 생성
                - Messenger 웹훅 설정
                """,
                metadata={"category": "channel_integration", "priority": "high"}
            ),
            Document(
                page_content="""
                AI 자동응답 기능
                
                드림위시는 GPT-4 기반 AI 챗봇을 제공합니다.
                
                **작동 방식:**
                1. 고객이 메시지 전송
                2. AI가 질문 의도 분석
                3. 지식베이스(PDF 학습 데이터)에서 관련 정보 검색
                4. GPT-4가 답변 생성
                5. 고객에게 실시간 전달
                
                **장점:**
                - 24시간 즉시 응답
                - 상담원 업무 부담 감소
                - 일관된 품질의 답변 제공
                - 복잡한 문의는 상담원에게 자동 전달
                """,
                metadata={"category": "ai_features", "priority": "high"}
            ),
        ]
        
        # FAISS 인덱스 생성
        self.vector_store = FAISS.from_documents(documents, self.embeddings)  # type: ignore[misc]
        self.vector_store.save_local(self.index_path)  # type: ignore[union-attr]
        
        print("✅ 기본 지식베이스 생성 완료")
        print("💡 PDF 이미지를 추가하려면 rebuild_from_pdf() 메서드를 호출하세요")
    
    async def rebuild_from_pdf(self):
        """PDF 이미지에서 텍스트를 추출하여 지식베이스 재구축"""
        
        if not LANGCHAIN_AVAILABLE or not Document:
            print("⚠️ LangChain이 설치되지 않아 지식베이스를 재구축할 수 없습니다.")
            return
        
        try:
            from backend.services.pdf_processor import pdf_processor
            
            # PDF 이미지에서 텍스트 추출
            pdf_documents = await pdf_processor.process_all_images()
            
            if not pdf_documents:
                print("⚠️ PDF 이미지에서 추출한 문서가 없습니다.")
                return
            
            # LangChain Document 객체로 변환
            documents = []
            for doc_data in pdf_documents:
                doc = Document(  # type: ignore[misc]
                    page_content=doc_data["page_content"],
                    metadata=doc_data["metadata"]
                )
                documents.append(doc)
            
            # 새 인덱스 생성
            self.vector_store = FAISS.from_documents(documents, self.embeddings)  # type: ignore[misc]
            self.vector_store.save_local(self.index_path)  # type: ignore[union-attr]
            
            print(f"✅ PDF 기반 지식베이스 재구축 완료 ({len(documents)}개 문서)")
        
        except Exception as e:
            print(f"❌ PDF 지식베이스 재구축 실패: {e}")
    
    def search(self, query: str, k: int = 3) -> List:  # type: ignore[type-arg]
        """
        질문과 유사한 지식 검색
        
        Args:
            query: 사용자 질문
            k: 반환할 문서 개수
            
        Returns:
            관련 문서 리스트
        """
        
        if not self.vector_store:
            self.load_or_create_index()
        
        if not self.vector_store:
            return []
        
        results = self.vector_store.similarity_search(query, k=k)  # type: ignore[union-attr]
        return results
    
    def add_document(self, content: str, metadata: Optional[Dict] = None):  # type: ignore[type-arg]
        """새로운 지식 추가"""
        
        if not self.vector_store or not Document:
            self.load_or_create_index()
        
        if not self.vector_store:
            print("⚠️ 지식베이스를 사용할 수 없습니다.")
            return
        
        doc = Document(page_content=content, metadata=metadata or {})  # type: ignore[misc]
        self.vector_store.add_documents([doc])  # type: ignore[union-attr]
        self.vector_store.save_local(self.index_path)  # type: ignore[union-attr]
        
        print(f"✅ 지식베이스에 문서 추가: {content[:50]}...")
    
    def get_context_for_query(self, query: str) -> str:
        """
        질문에 대한 컨텍스트 생성
        RAG에서 사용
        """
        
        docs = self.search(query, k=3)
        
        if not docs:
            return ""
        
        context = "\n\n=== 관련 지식 ===\n\n"
        for i, doc in enumerate(docs, 1):
            context += f"[문서 {i}]\n{doc.page_content}\n\n"
        
        return context


# 싱글톤 인스턴스
knowledge_base = KnowledgeBase()
