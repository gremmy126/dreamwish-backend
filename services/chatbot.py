"""
AI 챗봇 서비스
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
import os


async def generate_response(user_message: str) -> str:
    """AI 챗봇 응답 생성"""
    
    template = """당신은 드림위시의 고객 지원 AI 챗봇입니다.

규칙:
- 친절하고 전문적으로 답변하세요
- 모르는 내용은 상담원 연결을 제안하세요
- 간결하게 3-5문장으로 답변하세요

고객 질문: {question}

답변:"""
    
    try:
        prompt = PromptTemplate.from_template(template)
        model = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
        chain = prompt | model | StrOutputParser()
        
        response = chain.invoke({"question": user_message})
        return response
    
    except Exception as e:
        return "죄송합니다. 잠시 후 다시 시도해주세요."