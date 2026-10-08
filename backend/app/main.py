"""FastAPI application: startup/shutdown, CORS, error handlers and routers."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import DriverError, Neo4jError
from sqlalchemy.exc import InterfaceError, OperationalError

from app.api import auth, chat, health, memory, sessions, users
from app.brain.driver import create_driver
from app.brain.schema import setup_schema
from app.classifier.router import create_classifier
from app.config import get_settings
from app.db.engine import create_engine, create_session_factory
from app.llm.litellm_provider import create_llm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # One engine and one driver for the whole process, shared through app.state.
    app.state.engine = create_engine(settings.database_url)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.state.neo4j = create_driver(settings)
    app.state.llm = create_llm(settings)
    app.state.classifier = create_classifier(settings, app.state.llm)

    try:
        await setup_schema(app.state.neo4j)
    except Exception:
        # Start anyway so /health can report that Neo4j is down.
        logger.exception("Neo4j schema setup failed at startup")

    yield

    await app.state.classifier.aclose()
    await app.state.neo4j.close()
    await app.state.engine.dispose()


app = FastAPI(title="MyNaksh Astrology Chat", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Database outages become a friendly 503, never a stack trace -------------
# A route that can do something better than fail (like /chat when Neo4j is down)
# catches the error itself, so it never reaches these handlers.


# OSError: Postgres cannot be reached at all (connection refused, timeout).
# OperationalError / InterfaceError: the connection broke while in use.
@app.exception_handler(OSError)
@app.exception_handler(OperationalError)
@app.exception_handler(InterfaceError)
async def postgres_unavailable(request: Request, error: Exception) -> JSONResponse:
    logger.error("Postgres unavailable on %s %s: %r", request.method, request.url.path, error)
    return JSONResponse(
        status_code=503,
        content={"detail": "The service is temporarily unavailable. Please try again in a moment."},
    )


# DriverError: Neo4j cannot be reached. Neo4jError: the server returned an error.
@app.exception_handler(DriverError)
@app.exception_handler(Neo4jError)
async def neo4j_unavailable(request: Request, error: Exception) -> JSONResponse:
    logger.error("Neo4j unavailable on %s %s: %r", request.method, request.url.path, error)
    return JSONResponse(
        status_code=503,
        content={"detail": "Your profile is temporarily unavailable. Please try again in a moment."},
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(memory.router)
