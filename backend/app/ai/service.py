import asyncio

from .contracts import RecommendationOutcome, RecommendationRequest
from .engine import Member3Engine


class RecommendationService:
    """
    Backend-facing service for Member 3 AI recommendations.

    The service:
    - accepts a sanitized RecommendationRequest
    - invokes Member3Engine
    - enforces an 8-second timeout

    It never executes financial actions.
    """

    def __init__(
        self,
        engine: Member3Engine | None = None,
        timeout_seconds: float = 8.0,
    ):
        self.engine = engine or Member3Engine()
        self.timeout_seconds = timeout_seconds

    async def recommend(
        self,
        request: RecommendationRequest,
    ) -> RecommendationOutcome:
        try:
            return await asyncio.wait_for(
                self.engine.recommend(request),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return self.engine._model_error(
                request,
                error_code="TIMEOUT",
                retryable=True,
            )