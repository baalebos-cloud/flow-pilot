import asyncio

from pydantic import ValidationError

from app.ai.contracts import ModelFailure, RecommendationOutcome, RecommendationRequest, RecommendationResult
from app.ai.interface import RecommendationEngine
from app.ai.policy import ContractPolicyError, ValidatedRecommendation, validate_recommendation


class RecommendationService:
    def __init__(self, engine: RecommendationEngine, timeout_seconds: float = 8.0):
        self._engine = engine
        self._timeout_seconds = timeout_seconds

    async def recommend(
        self, request: RecommendationRequest
    ) -> ValidatedRecommendation | RecommendationOutcome:
        try:
            raw_outcome = await asyncio.wait_for(
                self._engine.recommend(request), timeout=self._timeout_seconds
            )
        except TimeoutError:
            return _failure(request.request_id, "TIMEOUT", retryable=True)
        except Exception:
            return _failure(request.request_id, "INTERNAL_ERROR", retryable=True)

        try:
            outcome = RecommendationOutcome.model_validate(raw_outcome)
        except ValidationError:
            return _failure(request.request_id, "INVALID_OUTPUT", retryable=False)

        value = outcome.root
        if not isinstance(value, RecommendationResult):
            return outcome
        try:
            return validate_recommendation(request, value)
        except ContractPolicyError:
            return _failure(request.request_id, "INVALID_OUTPUT", retryable=False)


def _failure(request_id: str, error_code: str, *, retryable: bool) -> RecommendationOutcome:
    return RecommendationOutcome(
        ModelFailure(
            outcome="MODEL_ERROR",
            request_id=request_id,
            error_code=error_code,
            retryable=retryable,
        )
    )
