"""GET /users/me and PUT /users/me/profile (the onboarding form)."""

from fastapi import APIRouter, Depends
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.brain import profile_repository
from app.brain.driver import get_driver
from app.db.engine import get_db
from app.db.models import UserRow
from app.models.profile import MeResponse, ProfileUpdate
from app.profile.service import save_profile_from_form

router = APIRouter(prefix="/users")


async def build_me_response(driver: AsyncDriver, user: UserRow) -> MeResponse:
    # Email and the flag come from Postgres; the profile and zodiac come from Neo4j.
    profile = await profile_repository.get_profile(driver, str(user.id))
    return MeResponse(email=user.email, profile_complete=user.profile_complete, profile=profile)


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: UserRow = Depends(get_current_user),
    driver: AsyncDriver = Depends(get_driver),
) -> MeResponse:
    return await build_me_response(driver, user)


@router.put("/me/profile", response_model=MeResponse)
async def update_profile(
    body: ProfileUpdate,
    user: UserRow = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    driver: AsyncDriver = Depends(get_driver),
) -> MeResponse:
    await save_profile_from_form(driver, db, user, body)
    return await build_me_response(driver, user)
