"""SQLAlchemy async engine and session factory for Postgres."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

CONNECT_TIMEOUT_SECONDS = 10


def asyncpg_url_and_args(database_url: str) -> tuple[URL, dict]:
    """Turn a standard Postgres URL (as Neon provides it) into what asyncpg needs.

    Neon's strings look like `postgresql://...?sslmode=require&channel_binding=require`.
    asyncpg does not understand those two query parameters, so they are removed from
    the URL and SSL is passed as a connect argument instead.
    """
    url = make_url(database_url)
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    url = url.set(drivername="postgresql+asyncpg", query=query)

    connect_args: dict = {
        "timeout": CONNECT_TIMEOUT_SECONDS,
        # Neon's pooled string goes through PgBouncer, which cannot keep prepared
        # statements across connections. Both caches are disabled so the same code
        # works for pooled and direct connections.
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }
    if sslmode:
        connect_args["ssl"] = sslmode
    return url, connect_args


def create_engine(database_url: str) -> AsyncEngine:
    url, connect_args = asyncpg_url_and_args(database_url)
    # pool_pre_ping tests a pooled connection before use, so a connection that
    # Neon closed while its compute was suspended is replaced instead of failing.
    return create_async_engine(url, connect_args=connect_args, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one database session per request."""
    async with request.app.state.session_factory() as session:
        yield session
