"""FastAPI application: startup/shutdown, CORS and routers."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.brain.driver import create_driver
from app.brain.schema import setup_schema
from app.config import get_settings
from app.db.engine import create_engine, create_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # One engine and one driver for the whole process, shared through app.state.
    app.state.engine = create_engine(settings.database_url)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.neo4j = create_driver(settings)

    try:
        await setup_schema(app.state.neo4j)
    except Exception:
        # Start anyway so /health can report that Neo4j is down.
        logger.exception("Neo4j schema setup failed at startup")

    yield

    await app.state.neo4j.close()
    await app.state.engine.dispose()


app = FastAPI(title="MyNaksh Astrology Chat", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
