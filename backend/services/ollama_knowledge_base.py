# backend/services/ollama_knowledge_base.py
"""
Ollama 기반 지식베이스
대시보드에서 업로드한 PDF 기반 FAISS 벡터 DB 사용
"""

import os
from pathlib import Path
from typing import List, Dict, Optional

try:
    from langchain_openai import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS
    LANGCHAIN_AVAILABLE = True
except ImportError:
    print("⚠️ LangChain 라이브러리가 설치되지 않았습니다. RAG 기능이 비활성화됩니다.")
    LANGCHAIN_AVAILABLE = False
    OpenAIEmbeddings = None  # type: ignore[misc,assignment]
    FAISS = None  # type: ignore[misc,assignment]


class OllamaKnowledgeBase:
    """
    대시보드 업로드 기반 지식베이스
    - FAISS 벡터 저장소 사용
    - OpenAI 임베딩
    - 대시보드에서 업로드한 PDF만 사용
    """
    
    def __init__(self):
        if not LANGCHAIN_AVAILABLE:
            self.vector_store = None
            self.faiss_path = "faiss_index"
            print("⚠️ LangChain이 설치되지 않아 지식베이스를 사용할 수 없습니다.")
            return
            
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")  # type: ignore[misc]
        self.vector_store = None
        self.faiss_path = "faiss_index"
        
        # 기존 인덱스 로드 시도
        self._load_index()
    
    def _load_index(self):
        """기존 FAISS 인덱스 로드"""
        if not LANGCHAIN_AVAILABLE:
            return
            
        if os.path.exists(self.faiss_path):
            try:
                self.vector_store = FAISS.load_local(  # type: ignore[misc]
                    self.faiss_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                print("✅ 대시보드 업로드 지식베이스 로드 완료")
            except Exception as e:
                print(f"⚠️ 지식베이스 로드 실패: {e}")
                self.vector_store = None
        else:
            print("⚠️ 아직 업로드된 PDF가 없습니다. 대시보드에서 PDF를 업로드하세요.")
    
    
    def search(self, query: str, k: int = 3) -> List[Dict]:
        """
        질문과 유사한 지식 검색
        
        Args:
            query: 사용자 질문
            k: 반환할 문서 개수
            
        Returns:
            관련 문서 리스트
        """
        
        if not LANGCHAIN_AVAILABLE or not self.vector_store:
            print("⚠️ 지식베이스가 없습니다. 대시보드에서 PDF를 업로드하세요.")
            return []
        
        try:
            # FAISS 검색
            docs = self.vector_store.similarity_search(query, k=k)
            
            # 결과 포맷팅
            documents = []
            for doc in docs:
                documents.append({
                    "page_content": doc.page_content,
                    "metadata": doc.metadata
                })
            
            return documents
        
        except Exception as e:
            print(f"❌ 지식 검색 실패: {e}")
            return []
    
    def get_context_for_query(self, query: str) -> str:
        """
        질문에 대한 컨텍스트 생성
        RAG에서 사용
        """
        
        docs = self.search(query, k=3)
        
        if not docs:
            return ""
        
        context = "\n\n=== 관련 지식 (대시보드 업로드 PDF) ===\n\n"
        for i, doc in enumerate(docs, 1):
            context += f"[문서 {i}]\n{doc['page_content']}\n\n"
        
        return context
    
    def reload_index(self):
        """지식베이스 인덱스 다시 로드"""
        self._load_index()


# 싱글톤 인스턴스
ollama_knowledge_base = OllamaKnowledgeBase()
