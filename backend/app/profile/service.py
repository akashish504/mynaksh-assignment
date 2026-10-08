"""Profile operations that touch both stores."""

from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain import profile_repository
from app.db import user_repository
from app.db.models import UserRow
from app.models.profile import ProfileUpdate
from app.profile.sun_sign import sun_sign_for


async def save_profile_from_form(
    driver: AsyncDriver, db: AsyncSession, user: UserRow, form: ProfileUpdate
) -> None:
    """Save the onboarding form.

    Write order: Neo4j first, then the Postgres flag. If the Postgres update fails
    the request fails and the user retries; the Neo4j write is safe to repeat.
    """
    await profile_repository.save_profile(
        driver,
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
    await user_repository.set_profile_complete(db, user.id)
    user.profile_complete = True
