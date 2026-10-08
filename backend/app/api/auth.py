"""POST /auth/signup and POST /auth/login."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import create_access_token
from app.brain.profile_repository import ProfileRepository, get_profile_repository
from app.db.user_repository import UserRepository, get_user_repository
from app.models.auth import LoginRequest, SignupRequest, TokenResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")

EMAIL_TAKEN = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="An account with this email already exists. Try logging in instead.",
)


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupRequest,
    users: UserRepository = Depends(get_user_repository),
    profiles: ProfileRepository = Depends(get_profile_repository),
) -> TokenResponse:
    email = body.email.lower()
    if await users.get_by_email(email) is not None:
        raise EMAIL_TAKEN

    # bcrypt is slow on purpose; run it in a thread so other requests are not blocked.
    password_hash = await asyncio.to_thread(hash_password, body.password)

    # Step 1: the Postgres row. Its id is reused as the Neo4j User.id.
    try:
        user = await users.create(email, password_hash)
    except IntegrityError:
        # Two signups with the same email at the same moment: the unique index stops the second.
        raise EMAIL_TAKEN

    # Step 2: the Neo4j User node with the same id.
    try:
        await profiles.merge_user(str(user.id))
    except Exception:
        # Step 3 (compensating action): there is no cross-store transaction, so the
        # Postgres row is removed by hand to avoid a user that exists in one store only.
        logger.exception("Signup: Neo4j write failed, removing Postgres user %s", user.id)
        await users.delete_by_id(user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We couldn't create your account right now. Please try again in a moment.",
        )

    return TokenResponse(access_token=create_access_token(user.id), profile_complete=False)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    users: UserRepository = Depends(get_user_repository),
) -> TokenResponse:
    # Postgres only; Neo4j is not involved in logging in.
    user = await users.get_by_email(body.email.lower())
    password_ok = user is not None and await asyncio.to_thread(
        verify_password, body.password, user.password_hash
    )
    if not password_ok:
        # Same message for "no such email" and "wrong password", so neither is revealed.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    return TokenResponse(
        access_token=create_access_token(user.id), profile_complete=user.profile_complete
    )
