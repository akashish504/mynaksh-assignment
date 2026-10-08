"""Rate limiting for /chat: a fixed number of requests per minute, per user.

The counters live in this process's memory. That is correct only while the API
runs as a single uvicorn worker (it does); with several workers or machines each
would count separately and a shared store would be needed.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.auth.tokens import read_user_id
from app.config import get_settings


def user_key(request: Request) -> str:
    """Who to count the request against: the user id inside the login token."""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    user_id = read_user_id(token)
    # Without a valid token the request is rejected with 401 anyway; the address
    # is only a fallback so there is always a key.
    return str(user_id) if user_id is not None else get_remote_address(request)


def chat_limit() -> str:
    return get_settings().chat_rate_limit


limiter = Limiter(key_func=user_key)


async def rate_limit_exceeded(request: Request, error: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "You're sending messages too quickly. Please wait a moment and try again."},
    )
