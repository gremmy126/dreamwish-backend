# backend/services/ollama_chatbot.py
"""
Ollama 기반 AI 챗봇 서비스
로컬에서 실행되는 LLM 사용
"""

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    ollama = None  # type: ignore

from typing import Optional, List, Dict
from datetime import datetime


class OllamaChatbot:
    """
    Ollama 기반 AI 챗봇
    - 로컬 LLM (llama3, mistral 등)
    - 드림위시 플랫폼 전문 상담
    - 대화 컨텍스트 유지
    """
    
    def __init__(self):
        self.available = OLLAMA_AVAILABLE
        self.model = "llama3.2:3b"  # 가벼운 모델 (3B 파라미터)
        self.max_tokens = 1000
        self.temperature = 0.7
        
        # 드림위시 시스템 프롬프트
        self.system_prompt = """당신은 '드림위시(Dreamwish)' 고객 지원 플랫폼 전문 AI 어시스턴트입니다.

**중요 제약사항:**
- 오직 드림위시 플랫폼 기능, 사용법, 서비스에 관한 질문에만 답변합니다
- 드림위시와 무관한 질문에는: "죄송합니다. 저는 드림위시 플랫폼 전문 상담 AI입니다. 드림위시 서비스 관련 질문만 답변 가능합니다."

**역할:**
- 드림위시 플랫폼 기능 및 사용법 안내
- 채팅 상담, 채널 연동, 팀원 관리 등 플랫폼 기능 설명
- 고객 지원 서비스 이용 방법 안내
- PDF 지식베이스의 드림위시 플랫폼 정보를 기반으로 답변

**답변 원칙:**
1. 친절하고 전문적인 어투 사용 (한국어)
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

**답변 형식:**
- 간결하고 명확하게 (200자 이내 권장)
- 필요시 번호 목록 사용
- 이모지 적절히 활용"""
    
    def should_auto_respond(self, message: str) -> bool:
        """
        AI 자동응답 여부 판단
        
        간단한 질문: AI 자동 응답
        복잡한 질문: 상담원 연결
        """
        # 간단한 키워드 기반 판단
        simple_keywords = [
            "안녕", "사용법", "방법", "기능", "채널", "연동",
            "위젯", "대시보드", "팀원", "초대", "가입", "로그인"
        ]
        
        return any(keyword in message for keyword in simple_keywords)
    
    async def get_response(
        self, 
        user_message: str, 
        conversation_history: Optional[List[Dict]] = None,
        context: Optional[str] = None
    ) -> str:
        """
        사용자 메시지에 대한 AI 응답 생성
        
        Args:
            user_message: 사용자 질문
            conversation_history: 이전 대화 내역
            context: 지식베이스에서 검색한 관련 정보
            
        Returns:
            AI 응답 텍스트
        """
        
        try:
            # 메시지 구성
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            # 컨텍스트 추가 (지식베이스 검색 결과)
            if context:
                messages.append({
                    "role": "system",
                    "content": f"참고 정보:\n{context}"
                })
            
            # 대화 히스토리 추가
            if conversation_history:
                for msg in conversation_history[-5:]:  # 최근 5개만
                    role = "user" if msg.get("sender_type") == "customer" else "assistant"
                    messages.append({
                        "role": role,
                        "content": msg.get("content", "")
                    })
            
            # 현재 질문
            messages.append({
                "role": "user",
                "content": user_message
            })
            
            # Ollama 사용 불가능한 경우
            if not self.available or not ollama:
                return "죄송합니다. 현재 AI 챗봇 서비스를 사용할 수 없습니다. 상담원과 연결해드리겠습니다."
            
            # Ollama API 호출
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            )
            
            answer = response['message']['content']
            
            # 응답 후처리
            answer = answer.strip()
            
            # 너무 길면 자르기
            if len(answer) > 500:
                answer = answer[:500] + "...\n\n더 자세한 내용은 상담원과 연결해드리겠습니다."
            
            return answer
        
        except Exception as e:
            print(f"❌ Ollama AI 응답 생성 실패: {e}")
            return "죄송합니다. 일시적인 오류가 발생했습니다. 상담원과 연결해드리겠습니다."
    
    async def analyze_intent(self, message: str) -> str:
        """메시지 의도 분석"""
        
        intents = {
            "인사": ["안녕", "hi", "hello", "반가"],
            "기능_문의": ["기능", "사용법", "방법", "어떻게"],
            "채널_연동": ["카카오", "인스타", "페이스북", "연동", "채널"],
            "문제_해결": ["오류", "안돼", "작동", "문제"],
            "기타": []
        }
        
        for intent, keywords in intents.items():
            if any(k in message for k in keywords):
                return intent
        
        return "기타"


# 싱글톤 인스턴스
ollama_chatbot = OllamaChatbot()
