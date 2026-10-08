"""The current-user dependency used by every protected endpoint."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import read_user_id
from app.db import user_repository
from app.db.engine import get_db
from app.db.models import UserRow

# auto_error=False so a missing header gives our own 401 below.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserRow:
    """Read `Authorization: Bearer <token>` and return the matching user.

    The user always comes from the token, never from the request body.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Please log in to continue.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    user_id = read_user_id(credentials.credentials)
    if user_id is None:
        raise unauthorized

    user = await user_repository.get_by_id(db, user_id)
    if user is None:
        raise unauthorized
    return user
