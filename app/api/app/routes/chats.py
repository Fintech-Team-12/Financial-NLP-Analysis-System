"""채팅 이력 관리 라우터."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, get_db
from app.db.models import User
from app.services import chat_history_service

router = APIRouter()

class ChatRenameRequest(BaseModel):
    title: str

@router.get("/chats")
def get_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """사용자의 채팅 세션 목록 조회."""
    sessions = chat_history_service.list_user_sessions(db, current_user.id)
    return [
        {
            "id": s.id,
            "title": s.title or "New Chat",
            "updated_at": s.updated_at.isoformat()
        } for s in sessions
    ]

@router.get("/chats/{chat_id}/messages")
def get_chat_messages(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """특정 채팅 세션의 메시지 목록 조회."""
    session_obj = chat_history_service.get_session_by_id(db, chat_id)
    if not session_obj or session_obj.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다.")

    messages = chat_history_service.list_session_messages(db, chat_id)
    return {
        "title": session_obj.title or "New Chat",
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat()
            } for m in messages
        ]
    }

@router.put("/chats/{chat_id}")
def rename_chat(
    chat_id: int,
    req: ChatRenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """채팅 세션 이름 변경."""
    session_obj = chat_history_service.get_session_by_id(db, chat_id)
    if not session_obj or session_obj.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다.")

    session_obj.title = req.title
    db.commit()
    return {"status": "success", "title": session_obj.title}

@router.delete("/chats/{chat_id}")
def delete_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """채팅 세션 완전 삭제."""
    session_obj = chat_history_service.get_session_by_id(db, chat_id)
    if not session_obj or session_obj.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다.")

    success = chat_history_service.delete_session(db, chat_id)
    if not success:
        raise HTTPException(status_code=500, detail="삭제 실패")
    
    db.commit()
    return {"status": "success"}
