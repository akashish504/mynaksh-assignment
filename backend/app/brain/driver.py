"""Neo4j driver creation and the FastAPI dependency that hands it to routes."""

from fastapi import Request
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import Settings

CONNECT_TIMEOUT_SECONDS = 5
# The driver retries a failed query by itself. Its default is to keep trying for 30
# seconds, which would leave a user waiting that long when Neo4j is down.
RETRY_SECONDS = 5


def create_driver(settings: Settings) -> AsyncDriver:
    # Creating the driver does not connect; the first query does.
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=CONNECT_TIMEOUT_SECONDS,
        max_transaction_retry_time=RETRY_SECONDS,
        # Neo4j warns when a query names a relationship type that no node has yet
        # (e.g. PREFERS before the first preference is stored). That is expected here.
        notifications_min_severity="OFF",
    )


def get_driver(request: Request) -> AsyncDriver:
    """FastAPI dependency: the one shared Neo4j driver."""
    return request.app.state.neo4j
