"""Profile operations that touch both stores."""

from fastapi import Depends

from app.brain.profile_repository import ProfileRepository, get_profile_repository
from app.db.models import UserRow
from app.db.user_repository import UserRepository, get_user_repository
from app.models.profile import MeResponse, ProfileUpdate
from app.profile.sun_sign import sun_sign_for


class ProfileService:
    def __init__(self, profiles: ProfileRepository, users: UserRepository):
        self.profiles = profiles
        self.users = users

    async def save_from_form(self, user: UserRow, form: ProfileUpdate) -> None:
        """Save the onboarding form.

        Write order: Neo4j first, then the Postgres flag. If the Postgres update fails
        the request fails and the user retries; the Neo4j write is safe to repeat.
        """
        await self.profiles.save_profile(
            user_id=str(user.id),
            name=form.name,
            dob=form.dob,
            birth_time=form.birth_time,
            birth_time_known=form.birth_time_known,
            birth_place=form.birth_place,
            language=form.language,
            # Always computed here from the date of birth, never taken from the user.
            sun_sign=sun_sign_for(form.dob),
            updated_via="form",
        )
        await self.users.set_profile_complete(user.id)
        user.profile_complete = True

    async def describe(self, user: UserRow) -> MeResponse:
        """Email and the flag come from Postgres; the profile and zodiac come from Neo4j."""
        profile = await self.profiles.get_profile(str(user.id))
        return MeResponse(email=user.email, profile_complete=user.profile_complete, profile=profile)


def get_profile_service(
    profiles: ProfileRepository = Depends(get_profile_repository),
    users: UserRepository = Depends(get_user_repository),
) -> ProfileService:
    return ProfileService(profiles, users)
