from app.main import app


class BrokenNeo4jDriver:
    async def execute_query(self, *args, **kwargs):
        raise ConnectionError("Neo4j is unreachable")


class BrokenEngine:
    def connect(self):
        raise ConnectionError("Postgres is unreachable")


async def test_health_reports_both_databases_up(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "postgres": "up", "neo4j": "up"}


async def test_health_reports_neo4j_down(client):
    real_driver = app.state.neo4j
    app.state.neo4j = BrokenNeo4jDriver()
    try:
        response = await client.get("/health")
    finally:
        app.state.neo4j = real_driver

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "postgres": "up", "neo4j": "down"}


async def test_health_reports_postgres_down(client):
    real_engine = app.state.engine
    app.state.engine = BrokenEngine()
    try:
        response = await client.get("/health")
    finally:
        app.state.engine = real_engine

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "postgres": "down", "neo4j": "up"}
