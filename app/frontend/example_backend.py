# =================================================================
# FastAPI Backend Example for Google OAuth & Chat History
# =================================================================
# 참고용으로 작성된 예시 데모 스크립트입니다.
# 실행: uvicorn example_backend:app --reload
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Header, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
import os
import jwt
from dotenv import load_dotenv
from google.oauth2 import id_token
from google.auth.transport import requests

# .env 파일 로드
load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "my_super_secret_jwt_key")
ALGORITHM = "HS256"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID_HERE.apps.googleusercontent.com")

# -----------------------------------------------------------------
# 1. Database & ORM Setup (SQLite 예시)
# -----------------------------------------------------------------
SQLALCHEMY_DATABASE_URL = "sqlite:///./example_finance.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)

    # 1:N Relation with Chats
    chats = relationship("Chat", back_populates="owner")

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    owner = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    chat_id = Column(Integer, ForeignKey("chats.id"))

    chat = relationship("Chat", back_populates="messages")

# Create tables in SQLite
Base.metadata.create_all(bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------------------------------------------
# 2. Pydantic Schemas
# -----------------------------------------------------------------
class TokenPayload(BaseModel):
    google_token: str

class MessageCreate(BaseModel):
    chat_id: Optional[int] = None
    question: str
    year: int

class ChatResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    class Config:
        orm_mode = True

class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    class Config:
        orm_mode = True


# -----------------------------------------------------------------
# 3. FastAPI App & Routes
# -----------------------------------------------------------------
app = FastAPI(title="Finance RAG Backend Example")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Authentication ---
def create_access_token(data: dict):
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)):
    """
    프론트에서 전달받은 JWT 기반으로 사용자 객체를 리턴합니다.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    token = authorization.split(" ")[1]
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token Invalid")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token Invalid or Expired")
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@app.post("/api/auth/google")
def google_auth(payload: TokenPayload, db: Session = Depends(get_db)):
    """
    google_token 검증 및 회원가입/로그인 처리
    """
    try:
        # 🚨 디버깅 통과 로직 추가 🚨
        if payload.google_token == "dummy_google_credential_for_bypassing_auth":
            google_info = {
                "sub": "user_debug_999",
                "email": "debug_user@example.com",
                "name": "개발자(Debug)"
            }
        elif GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID_HERE.apps.googleusercontent.com":
            # 더미 클라이언트 ID가 쓰인 경우 (테스트 모드: 아무 올바른 형식 JWT나 허용)
            decoded = jwt.decode(payload.google_token, options={"verify_signature": False})
            google_info = {
                "sub": decoded.get("sub", payload.google_token),
                "email": decoded.get("email", "mock@example.com"),
                "name": decoded.get("name", "Mocked User")
            }
        else:
            # 실제 구글 검증 로직
            google_info = id_token.verify_oauth2_token(
                payload.google_token, requests.Request(), GOOGLE_CLIENT_ID
            )
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid Token: {str(e)}")
    
    # DB에서 유저 조회, 없으면 생성
    user = db.query(User).filter(User.google_id == google_info["sub"]).first()
    if not user:
        user = User(
            google_id=google_info["sub"],
            email=google_info.get("email", ""),
            name=google_info.get("name", "")
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # JWT 엑세스 토큰 발급
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_info": {"id": user.id, "name": user.name, "email": user.email}
    }

# --- Chats ---
@app.get("/api/chats", response_model=List[ChatResponse])
def get_user_chats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """사용자가 소유한 과거 채팅 이력 리스트 반환"""
    chats = db.query(Chat).filter(Chat.user_id == current_user.id).order_by(Chat.created_at.desc()).all()
    return chats

@app.get("/api/chats/{chat_id}/messages", response_model=List[MessageResponse])
def get_chat_messages(chat_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """특정 채팅방의 메시지들 반환"""
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return chat.messages

@app.post("/api/chat")
def ask_question(
    req: MessageCreate, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    멀티턴 채팅 메인 로직
    """
    # 1. 방이 지정되지 않았다면 새 방을 생성
    if not req.chat_id:
        chat = Chat(user_id=current_user.id, title=req.question[:20])
        db.add(chat)
        db.commit()
        db.refresh(chat)
        chat_id = chat.id
    else:
        chat_id = req.chat_id
        
    # 2. 사용자 질문 저장
    user_msg = Message(chat_id=chat_id, role="user", content=req.question)
    db.add(user_msg)
    db.commit()
    
    # [백엔드 RAG 및 LLM 로직 수행 영역]
    # 이전 메시지 컨텍스트(chat.messages)와 RAG 지식을 결합해 LLM 돌리는 코드...
    # answer = llm_chain.invoke(req.question, context=...)
    answer = f"[{req.year}년] 질문 '{req.question}' 에 대한 백엔드 LLM 답변입니다."
    
    # 3. LLM 결과 저장
    assistant_msg = Message(chat_id=chat_id, role="assistant", content=answer)
    db.add(assistant_msg)
    db.commit()

    return {
        "answer": answer,
        "chat_id": chat_id
    }

# --- File Upload ---
@app.post("/api/files/upload")
def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    RAG용 파서 및 임베딩 로직용 엔드포인트
    """
    import shutil
    import os
    
    # 파일 저장 예시
    os.makedirs("./uploaded_files", exist_ok=True)
    file_location = f"./uploaded_files/{file.filename}"
    
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
        
    # RAG 파이프라인 수행 로직
    # embed_and_store(file_location)
        
    return {"info": f"file '{file.filename}' saved.", "user": current_user.name}
