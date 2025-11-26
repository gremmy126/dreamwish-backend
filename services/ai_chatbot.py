# backend/services/ai_chatbot.py
"""
AI 챗봇 서비스 - GPT 기반 자동 응답
드림위시 아파트 청약 관련 지식베이스 활용
"""

import os
from openai import AsyncOpenAI
from typing import Optional, List, Dict
import json
from datetime import datetime

# OpenAI 클라이언트
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


class AIChatbot:
    """
    GPT 기반 AI 챗봇
    - 아파트 청약 FAQ 자동 응답
    - 문서/이미지 분석 (Vision API)
    - 대화 컨텍스트 유지
    """
    
    def __init__(self):
        self.model = "gpt-4o"  # GPT-4 Omni (텍스트 + 이미지)
        self.max_tokens = 1000
        self.temperature = 0.7
        
        # 드림위시 시스템 프롬프트
        self.system_prompt = """
당신은 '드림위시(Dreamwish)' 고객 지원 플랫폼 전문 AI 어시스턴트입니다.

**중요 제약사항:**
- 오직 드림위시 플랫폼 기능, 사용법, 서비스에 관한 질문에만 답변합니다
- 드림위시와 무관한 질문(일반 상식, 날씨, 요리, 프로그래밍 등)에는 답변하지 않습니다
- 무관한 질문 시: "죄송합니다. 저는 드림위시 플랫폼 전문 상담 AI입니다. 드림위시 서비스 관련 질문만 답변 가능합니다."

**역할:**
- 드림위시 플랫폼 기능 및 사용법 안내
- 채팅 상담, 채널 연동, 팀원 관리 등 플랫폼 기능 설명
- 고객 지원 서비스 이용 방법 안내
- PDF 지식베이스의 드림위시 플랫폼 정보를 기반으로 답변

**답변 원칙:**
1. 친절하고 전문적인 어투 사용
2. 복잡한 기능은 단계별로 설명
3. 확실하지 않은 정보는 "상담원 연결"을 권유
4. 개인정보는 절대 요청하지 않음
5. 플랫폼과 무관한 질문은 정중히 거부

**주요 지식 영역:**
- 드림위시 플랫폼 주요 기능 (채팅 상담, AI 자동응답)
- 채널 연동 방법 (카카오톡, 인스타그램, 페이스북, 웹 위젯)
- 상담원 대시보드 사용법
- 팀원 초대 및 관리 방법
- 실시간 채팅 및 대화 관리 기능
- 대출 및 세금 정보

**제약사항:**
- 법률 자문은 불가 (전문가 상담 권유)
- 개별 투자 조언 제공 불가
- 실시간 분양 정보는 공식 사이트 확인 권유

고객의 질문에 따뜻하고 도움이 되는 답변을 제공하세요.
"""
    
    async def get_response(
        self, 
        user_message: str, 
        conversation_history: Optional[List[Dict]] = None,  # type: ignore[type-arg]
        image_urls: Optional[List[str]] = None
    ) -> str:
        """
        AI 응답 생성
        
        Args:
            user_message: 사용자 메시지
            conversation_history: 이전 대화 내역
            image_urls: 분석할 이미지 URL 리스트
            
        Returns:
            AI 생성 응답
        """
        
        if not client.api_key:
            return "⚠️ AI 서비스가 설정되지 않았습니다. 잠시 후 상담원이 응답하겠습니다."
        
        try:
            # 메시지 구성
            messages: List[Dict] = [  # type: ignore[type-arg]
                {"role": "system", "content": self.system_prompt}
            ]
            
            # 대화 히스토리 추가
            if conversation_history:
                for msg in conversation_history[-10:]:  # 최근 10개만
                    role = "user" if msg["sender_type"] == "customer" else "assistant"
                    messages.append({
                        "role": role,
                        "content": msg["content"]
                    })
            
            # 현재 메시지 추가
            if image_urls:
                # 이미지가 있는 경우 (Vision API)
                content = [
                    {"type": "text", "text": user_message}
                ]
                for url in image_urls:
                    content.append({  # type: ignore[arg-type]
                        "type": "image_url",
                        "image_url": {"url": url}
                    })
                messages.append({
                    "role": "user",
                    "content": content  # type: ignore[dict-item]
                })
            else:
                # 텍스트만 있는 경우
                messages.append({
                    "role": "user",
                    "content": user_message
                })
            
            # OpenAI API 호출
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            ai_message = response.choices[0].message.content
            
            if not ai_message:
                return "죄송합니다. 응답을 생성할 수 없습니다."
            
            print(f"✅ AI 응답 생성 완료: {ai_message[:100]}...")
            return ai_message
            
        except Exception as e:
            print(f"❌ AI 응답 생성 오류: {e}")
            return "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주시거나 상담원 연결을 요청해주세요."
    
    async def get_response_with_context(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict]] = None,  # type: ignore[type-arg]
        context: str = ""
    ) -> str:
        """
        지식베이스 컨텍스트를 활용한 AI 응답 생성
        
        Args:
            user_message: 사용자 메시지
            conversation_history: 이전 대화 내역
            context: 지식베이스에서 검색한 관련 문서 컨텍스트
            
        Returns:
            AI 생성 응답
        """
        
        if not client.api_key:
            return "⚠️ AI 서비스가 설정되지 않았습니다. 잠시 후 상담원이 응답하겠습니다."
        
        try:
            # 시스템 프롬프트에 컨텍스트 추가
            enhanced_system_prompt = self.system_prompt
            if context:
                enhanced_system_prompt += f"\n\n**참고 문서:**\n{context}\n\n위 문서 내용을 참고하여 답변해주세요."
            
            # 메시지 구성
            messages: List[Dict] = [  # type: ignore[type-arg]
                {"role": "system", "content": enhanced_system_prompt}
            ]
            
            # 대화 히스토리 추가
            if conversation_history:
                for msg in conversation_history[-10:]:  # 최근 10개만
                    role = "user" if msg["sender_type"] == "customer" else "assistant"
                    messages.append({
                        "role": role,
                        "content": msg["content"]
                    })
            
            # 현재 메시지 추가
            messages.append({
                "role": "user",
                "content": user_message
            })
            
            # OpenAI API 호출
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            ai_message = response.choices[0].message.content
            
            if not ai_message:
                return "죄송합니다. 응답을 생성할 수 없습니다."
            
            print(f"✅ AI 응답 생성 완료 (RAG): {ai_message[:100]}...")
            return ai_message
            
        except Exception as e:
            print(f"❌ AI 응답 생성 오류: {e}")
            return "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주시거나 상담원 연결을 요청해주세요."
    
    async def analyze_document(self, file_url: str, file_type: str) -> str:
        """
        문서 분석 (이미지 OCR, PDF 텍스트 추출)
        
        Args:
            file_url: 파일 URL
            file_type: 파일 타입 (image/pdf/document)
            
        Returns:
            분석 결과 텍스트
        """
        
        try:
            if file_type in ["image", "jpg", "jpeg", "png"]:
                # 이미지 분석 (Vision API)
                response = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=[  # type: ignore[arg-type]
                        {
                            "role": "system",
                            "content": "이미지에서 텍스트를 추출하고 주요 내용을 요약하세요. 아파트 청약 관련 문서라면 핵심 정보를 정리해주세요."
                        },
                        {
                            "role": "user",
                            "content": [  # type: ignore[dict-item]
                                {"type": "text", "text": "이 이미지를 분석해주세요."},
                                {"type": "image_url", "image_url": {"url": file_url}}
                            ]
                        }
                    ],
                    max_tokens=1500
                )
                
                return response.choices[0].message.content or "분석 결과를 가져올 수 없습니다."
            
            elif file_type == "pdf":
                # PDF는 별도 라이브러리 필요 (PyPDF2, pdfplumber 등)
                return "PDF 파일 분석 기능은 준비 중입니다."
            
            else:
                return "지원하지 않는 파일 형식입니다."
                
        except Exception as e:
            print(f"❌ 문서 분석 오류: {e}")
            return "문서 분석 중 오류가 발생했습니다."
    
    def should_auto_respond(self, message: str) -> bool:
        """
        자동 응답 여부 판단
        
        - 간단한 인사: 자동 응답 O
        - FAQ 질문: 자동 응답 O
        - 복잡한 상담: 상담원 연결 권유
        """
        
        # 간단한 키워드 기반 판단 (실제로는 더 정교한 로직 필요)
        simple_keywords = ["안녕", "문의", "궁금", "질문", "알려", "뭐", "어떻게"]
        complex_keywords = ["계약", "법률", "소송", "긴급", "상담원", "직접"]
        
        message_lower = message.lower()
        
        # 복잡한 키워드 포함 시 상담원 연결
        if any(kw in message_lower for kw in complex_keywords):
            return False
        
        # 간단한 질문은 자동 응답
        return True
    
    def create_handoff_message(self) -> str:
        """상담원 연결 메시지"""
        return """
🙋‍♂️ **상담원 연결**

더 자세한 상담이 필요하신 것 같습니다.
잠시만 기다려주시면 전문 상담원이 곧 응답드리겠습니다.

⏰ 평균 대기 시간: 2-3분
"""


# 싱글톤 인스턴스
ai_chatbot = AIChatbot()
