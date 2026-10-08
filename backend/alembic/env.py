"""Alembic entry point: runs migrations over an async (asyncpg) connection."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db.engine import asyncpg_url_and_args
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False keeps the app's and pytest's loggers working
    # when migrations are run from inside Python (as the test suite does).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # Migrations use the direct connection string, not the pooled one.
    url, connect_args = asyncpg_url_and_args(get_settings().migration_database_url)
    # NullPool: open one connection, migrate, close. Nothing is kept around.
    engine = create_async_engine(url, connect_args=connect_args, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


asyncio.run(run_migrations_online())
