"""POST /chat: one conversation turn."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.chat.pipeline import ChatPipeline, SessionNotFound, get_chat_pipeline
from app.db.models import UserRow
from app.models.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: UserRow = Depends(get_current_user),
    pipeline: ChatPipeline = Depends(get_chat_pipeline),
) -> ChatResponse:
    try:
        return await pipeline.handle_turn(user, body.session_id, body.message)
    except SessionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")
