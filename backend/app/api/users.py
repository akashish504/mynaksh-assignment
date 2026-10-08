"""GET /users/me and PUT /users/me/profile (the onboarding form)."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.db.models import UserRow
from app.models.profile import MeResponse, ProfileUpdate
from app.profile.service import ProfileService, get_profile_service

router = APIRouter(prefix="/users")


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: UserRow = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> MeResponse:
    return await service.describe(user)


@router.put("/me/profile", response_model=MeResponse)
async def update_profile(
    body: ProfileUpdate,
    user: UserRow = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> MeResponse:
    await service.save_from_form(user, body)
    return await service.describe(user)
