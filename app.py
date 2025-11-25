"""
드림위시 CS 챗봇 - Streamlit 메인 애플리케이션
"""

import streamlit as st
import streamlit.components.v1 as components
from streamlit.runtime.uploaded_file_manager import UploadedFile

# LangChain imports
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.documents.base import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable
from langchain_core.output_parsers import StrOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyMuPDFLoader

# Other imports
from dotenv import load_dotenv
from typing import List, Tuple
import fitz  # PyMuPDF
import os


# 환경변수 로드
load_dotenv(override=True)


############################### PDF 처리 함수 ##########################

def save_uploadedfile(uploadedfile: UploadedFile) -> str:
    """업로드된 PDF 파일을 임시 폴더에 저장"""
    temp_dir = "PDF_임시폴더"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    file_path = os.path.join(temp_dir, uploadedfile.name)
    with open(file_path, "wb") as f:
        f.write(uploadedfile.read())
    
    return file_path


def pdf_to_documents(pdf_path: str) -> List[Document]:
    """PDF 파일을 Document 객체로 변환"""
    loader = PyMuPDFLoader(pdf_path)
    documents = loader.load()
    
    for d in documents:
        d.metadata["file_path"] = pdf_path
    
    return documents


def chunk_documents(documents: List[Document]) -> List[Document]:
    """Document를 작은 청크로 분할"""
    # 빈 문서 제거
    documents = [
        d for d in documents
        if getattr(d, "page_content", None) and d.page_content.strip()
    ]
    
    if not documents:
        return []

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
    )
    chunks = text_splitter.split_documents(documents)

    # 빈 청크 제거
    chunks = [
        c for c in chunks
        if getattr(c, "page_content", None) and c.page_content.strip()
    ]
    
    return chunks


def save_to_vector_store(documents: List[Document]) -> bool:
    """Document를 FAISS 벡터 DB에 저장"""
    documents = [
        d for d in documents
        if getattr(d, "page_content", None) and d.page_content.strip()
    ]

    if not documents:
        st.error("텍스트를 추출한 문서가 없습니다. PDF 안에 텍스트가 있는지 확인해주세요.")
        return False

    try:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        vector_store = FAISS.from_documents(documents, embedding=embeddings)
        vector_store.save_local("faiss_index")
        st.success(f"✅ 벡터DB에 {len(documents)}개의 청크가 저장되었습니다!")
        return True
    except Exception as e:
        st.error(f"❌ 임베딩 생성 실패: {str(e)}")
        return False


def convert_pdf_to_images(pdf_path: str, dpi: int = 250) -> List[str]:
    """PDF 페이지를 이미지로 변환"""
    doc = fitz.open(pdf_path)
    image_paths: List[str] = []

    output_folder = "PDF_이미지"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        image_path = os.path.join(output_folder, f"page_{page_num + 1}.png")
        pix.save(image_path)
        image_paths.append(image_path)

    return image_paths


def display_pdf_page(image_path: str, page_number: int) -> None:
    """PDF 페이지 이미지 표시"""
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        st.image(image_bytes, caption=f"📄 Page {page_number}", output_format="PNG", width=600)
    except Exception as e:
        st.error(f"이미지 로드 실패: {str(e)}")


############################### RAG 처리 함수 ##########################

def get_rag_chain() -> Runnable:
    """RAG 체인 생성"""
    template = """다음의 컨텍스트를 활용해서 질문에 답변해주세요.

규칙:
- 질문에 대한 명확한 응답을 제공하세요
- 간결하게 5줄 이내로 답변하세요
- 컨텍스트에 없는 내용은 "해당 정보를 문서에서 찾을 수 없습니다"라고 답변하세요

컨텍스트: {context}

질문: {question}

답변:"""

    prompt = PromptTemplate.from_template(template)
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    return prompt | model | StrOutputParser()


def process_question(user_question: str) -> Tuple[str, List[Document]]:
    """사용자 질문 처리 및 응답 생성"""
    try:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        db = FAISS.load_local(
            "faiss_index",
            embeddings,
            allow_dangerous_deserialization=True,
        )
        
        retriever = db.as_retriever(search_kwargs={"k": 5})
        docs = retriever.invoke(user_question)
        
        chain = get_rag_chain()
        response = chain.invoke({"question": user_question, "context": docs})
        
        return response, docs
    
    except Exception as e:
        return f"오류 발생: {str(e)}", []


############################### Streamlit UI ##########################

def render_header():
    """헤더 렌더링"""
    st.markdown(
        """
        <div style="
            width:100%;
            padding:24px 0;
            background:linear-gradient(135deg,#6366F1,#8B5CF6);
            text-align:center;
            border-radius: 0 0 20px 20px;
            margin-bottom: 32px;
            box-shadow: 0 8px 32px rgba(99, 102, 241, 0.3);">
            <span style="font-size:32px; font-weight:800; color:white;">
                💬 Dreamwish CS Assistant
            </span>
            <p style="color:rgba(255,255,255,0.9); font-size:14px; margin-top:8px;">
                AI 기반 고객 지원 챗봇
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar():
    """사이드바 렌더링"""
    with st.sidebar:
        st.title("📋 시스템 정보")
        
        # 상태 표시
        if os.path.exists("faiss_index"):
            st.success("✅ 벡터 DB 준비됨")
        else:
            st.warning("⚠️ PDF를 업로드하세요")
        
        st.markdown("---")
        
        # 통계
        st.subheader("📊 통계")
        
        if "messages" in st.session_state:
            msg_count = len([m for m in st.session_state.messages if m["role"] == "user"])
            st.metric("총 질문 수", msg_count)
        
        st.markdown("---")
        
        # 정보
        st.subheader("ℹ️ 사용 방법")
        st.markdown("""
        1. PDF 파일 업로드
        2. 업로드 버튼 클릭
        3. 채팅창에서 질문 입력
        4. AI 답변 확인
        """)
        
        st.markdown("---")
        st.caption("© 2025 Dreamwish")


def main():
    """메인 애플리케이션"""
    
    # 페이지 설정
    st.set_page_config(
        page_title="드림위시 CS 챗봇",
        page_icon="💬",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 사이드바
    render_sidebar()
    
    # 헤더
    render_header()
    
    # 메인 레이아웃
    col1, col2 = st.columns([1, 1], gap="large")
    
    # =================== 왼쪽 컬럼: PDF 업로드 & 채팅 ===================
    with col1:
        # PDF 업로드 섹션
        with st.container():
            st.subheader("📄 PDF 문서 업로드")
            
            pdf_doc = st.file_uploader(
                "PDF 파일을 선택하세요",
                type=["pdf"],
                help="드림위시 관련 문서를 업로드하세요"
            )
            
            col_btn1, col_btn2 = st.columns([1, 1])
            
            with col_btn1:
                upload_btn = st.button(
                    "📤 PDF 업로드하기",
                    type="primary",
                    use_container_width=True
                )
            
            with col_btn2:
                if st.button("🗑️ 데이터 초기화", use_container_width=True):
                    if os.path.exists("faiss_index"):
                        import shutil
                        shutil.rmtree("faiss_index")
                        st.success("벡터 DB가 초기화되었습니다.")
                        st.rerun()
            
            if upload_btn and pdf_doc:
                with st.spinner("📚 PDF 처리 중..."):
                    # PDF 저장
                    pdf_path = save_uploadedfile(pdf_doc)
                    
                    # Document 변환
                    pdf_documents = pdf_to_documents(pdf_path)
                    st.info(f"📖 원본 문서: {len(pdf_documents)} 페이지")
                    
                    # 청크 분할
                    smaller_documents = chunk_documents(pdf_documents)
                    st.info(f"✂️ 청크 분할: {len(smaller_documents)}개")
                    
                    # 벡터 DB 저장
                    if save_to_vector_store(smaller_documents):
                        # 이미지 변환
                        with st.spinner("🖼️ 페이지 이미지 생성 중..."):
                            images = convert_pdf_to_images(pdf_path)
                            st.session_state["images"] = images
                            st.session_state["pdf_path"] = pdf_path
                        
                        st.balloons()
        
        st.markdown("---")
        
        # 채팅 섹션
        with st.container():
            st.subheader("💬 AI 챗봇")
            
            # 세션 초기화
            if "messages" not in st.session_state:
                st.session_state.messages = [
                    {
                        "role": "assistant",
                        "content": "안녕하세요! 드림위시 CS 챗봇입니다. 👋\n\n드림위시 플랫폼에 대해 궁금한 점을 물어보세요!"
                    }
                ]
            
            # 메시지 히스토리 표시
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            
            # 채팅 입력
            if prompt := st.chat_input("질문을 입력하세요..."):
                # 사용자 메시지 추가
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                # 봇 응답 생성
                if os.path.exists("faiss_index"):
                    with st.chat_message("assistant"):
                        with st.spinner("🤔 답변 생성 중..."):
                            response, docs = process_question(prompt)
                            st.markdown(response)
                            
                            # 참고 문서 표시
                            if docs:
                                with st.expander("📚 참고한 문서 보기"):
                                    for i, doc in enumerate(docs[:3], 1):
                                        st.caption(f"**문서 {i}**")
                                        st.text(doc.page_content[:200] + "...")
                                        st.markdown("---")
                        
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response
                        })
                else:
                    with st.chat_message("assistant"):
                        msg = "⚠️ 먼저 PDF를 업로드해주세요."
                        st.warning(msg)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": msg
                        })
    
    # =================== 오른쪽 컬럼: 챗봇 UI 프리뷰 & 페이지 미리보기 ===================
    with col2:
        # 챗봇 UI 프리뷰
        with st.container():
            st.subheader("🎨 챗봇 UI 프리뷰")
            
            try:
                with open("index.html", encoding="utf-8") as f:
                    html_content = f.read()
                
                components.html(html_content, height=600, scrolling=True)
            
            except FileNotFoundError:
                st.error("⚠️ index.html 파일을 찾을 수 없습니다.")
                st.info("프로젝트 폴더에 index.html 파일을 추가해주세요.")
        
        st.markdown("---")
        
        # PDF 페이지 미리보기
        with st.container():
            st.subheader("📖 PDF 페이지 미리보기")
            
            images = st.session_state.get("images", [])
            
            if images:
                page_num = st.slider(
                    "페이지 선택",
                    min_value=1,
                    max_value=len(images),
                    value=1,
                    help="슬라이더를 움직여 페이지를 선택하세요"
                )
                
                display_pdf_page(images[page_num - 1], page_num)
            else:
                st.info("📄 PDF를 업로드하면 페이지 미리보기를 볼 수 있습니다.")


if __name__ == "__main__":
    main()