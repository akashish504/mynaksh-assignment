"""Postgres access for the users table."""

import uuid

from fastapi import Depends
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import UserRow


class UserRepository:
    """All queries on the users table. Each method is one complete transaction."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str) -> UserRow | None:
        result = await self.db.execute(select(UserRow).where(UserRow.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> UserRow | None:
        return await self.db.get(UserRow, user_id)

    async def create(self, email: str, password_hash: str) -> UserRow:
        user = UserRow(email=email, password_hash=password_hash, profile_complete=False)
        self.db.add(user)
        try:
            await self.db.commit()
        except Exception:
            # Leave the session usable for the caller (e.g. after a duplicate email).
            await self.db.rollback()
            raise
        return user

    async def delete_by_id(self, user_id: uuid.UUID) -> None:
        await self.db.execute(delete(UserRow).where(UserRow.id == user_id))
        await self.db.commit()

    async def set_profile_complete(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(UserRow).where(UserRow.id == user_id).values(profile_complete=True)
        )
        await self.db.commit()


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    """FastAPI dependency: a UserRepository bound to this request's database session."""
    return UserRepository(db)
