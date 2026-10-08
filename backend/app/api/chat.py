"""POST /chat: one conversation turn."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.api.rate_limit import chat_limit, limiter
from app.auth.dependencies import get_current_user
from app.chat.pipeline import ChatPipeline, SessionNotFound, get_chat_pipeline
from app.db.models import UserRow
from app.memory.task import MemoryTask, get_memory_task
from app.models.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(chat_limit)
async def chat(
    request: Request,  # read by the rate limiter to find out who is calling
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: UserRow = Depends(get_current_user),
    pipeline: ChatPipeline = Depends(get_chat_pipeline),
    memory_task: MemoryTask = Depends(get_memory_task),
) -> ChatResponse:
    try:
        result = await pipeline.handle_turn(user, body.session_id, body.message)
    except SessionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")

    if result.memory_job is not None:
        # Runs after the response has been sent, so the user never waits for it.
        background_tasks.add_task(memory_task.run, result.memory_job)
    return result.response
