"""A scripted classifier for tests. It never calls a real API."""

from app.classifier.base import RouteResult
from app.db.models import MessageRow


class FakeClassifier:
    """Returns the queued RouteResults in order, then repeats the last one."""

    def __init__(self, *results: RouteResult):
        self.results = list(results)
        self.calls: list[tuple[list[MessageRow], str]] = []

    async def route(self, history: list[MessageRow], message: str) -> RouteResult:
        self.calls.append((history, message))
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]
