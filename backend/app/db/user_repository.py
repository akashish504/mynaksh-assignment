"""Postgres queries for the users table."""

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserRow


async def get_by_email(db: AsyncSession, email: str) -> UserRow | None:
    result = await db.execute(select(UserRow).where(UserRow.email == email))
    return result.scalar_one_or_none()


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> UserRow | None:
    return await db.get(UserRow, user_id)


async def create(db: AsyncSession, email: str, password_hash: str) -> UserRow:
    user = UserRow(email=email, password_hash=password_hash, profile_complete=False)
    db.add(user)
    await db.commit()
    return user


async def delete_by_id(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(UserRow).where(UserRow.id == user_id))
    await db.commit()


async def set_profile_complete(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(update(UserRow).where(UserRow.id == user_id).values(profile_complete=True))
    await db.commit()
