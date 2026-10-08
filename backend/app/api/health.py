"""GET /health: reports Postgres and Neo4j status separately."""

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from neo4j import AsyncDriver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.health import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Long enough for Neon to wake its compute after being idle.
CHECK_TIMEOUT_SECONDS = 10


async def postgres_is_up(engine: AsyncEngine) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Health check: Postgres is down")
        return False


async def neo4j_is_up(driver: AsyncDriver) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await driver.execute_query("RETURN 1")
        return True
    except Exception:
        logger.exception("Health check: Neo4j is down")
        return False


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def health(request: Request) -> JSONResponse:
    postgres_up, neo4j_up = await asyncio.gather(
        postgres_is_up(request.app.state.engine),
        neo4j_is_up(request.app.state.neo4j),
    )
    all_up = postgres_up and neo4j_up
    body = HealthResponse(
        status="ok" if all_up else "degraded",
        postgres="up" if postgres_up else "down",
        neo4j="up" if neo4j_up else "down",
    )
    # 503 when anything is down, so an uptime check can tell from the status code alone.
    return JSONResponse(body.model_dump(), status_code=200 if all_up else 503)
