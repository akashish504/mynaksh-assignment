from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: Literal["up", "down"]
    neo4j: Literal["up", "down"]
