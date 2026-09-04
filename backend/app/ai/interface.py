from typing import Protocol

from app.ai.contracts import RecommendationOutcome, RecommendationRequest


class RecommendationEngine(Protocol):
    async def recommend(self, request: RecommendationRequest) -> RecommendationOutcome:
        """Return a typed outcome without performing I/O outside the model provider."""
        ...

