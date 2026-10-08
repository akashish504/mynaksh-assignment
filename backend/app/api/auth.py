"""POST /auth/signup and POST /auth/login."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import AsyncDriver
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import create_access_token
from app.brain import profile_repository
from app.brain.driver import get_driver
from app.db import user_repository
from app.db.engine import get_db
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
    db: AsyncSession = Depends(get_db),
    driver: AsyncDriver = Depends(get_driver),
) -> TokenResponse:
    email = body.email.lower()
    if await user_repository.get_by_email(db, email) is not None:
        raise EMAIL_TAKEN

    # bcrypt is slow on purpose; run it in a thread so other requests are not blocked.
    password_hash = await asyncio.to_thread(hash_password, body.password)

    # Step 1: the Postgres row. Its id is reused as the Neo4j User.id.
    try:
        user = await user_repository.create(db, email, password_hash)
    except IntegrityError:
        # Two signups with the same email at the same moment: the unique index stops the second.
        await db.rollback()
        raise EMAIL_TAKEN

    # Step 2: the Neo4j User node with the same id.
    try:
        await profile_repository.merge_user(driver, str(user.id))
    except Exception:
        # Step 3 (compensating action): there is no cross-store transaction, so the
        # Postgres row is removed by hand to avoid a user that exists in one store only.
        logger.exception("Signup: Neo4j write failed, removing Postgres user %s", user.id)
        await user_repository.delete_by_id(db, user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We couldn't create your account right now. Please try again in a moment.",
        )

    return TokenResponse(access_token=create_access_token(user.id), profile_complete=False)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    # Postgres only; Neo4j is not involved in logging in.
    user = await user_repository.get_by_email(db, body.email.lower())
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
