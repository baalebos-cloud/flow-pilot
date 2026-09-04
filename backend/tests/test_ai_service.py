import asyncio

import pytest

from app.ai.contracts import RecommendationOutcome
from app.ai.policy import ValidatedRecommendation
from app.ai.service import RecommendationService
from tests.test_ai_contracts import recommendation_fixture, request_fixture


class FakeEngine:
    def __init__(self, result):
        self.result = result

    async def recommend(self, _request):
        return self.result


class SlowEngine:
    async def recommend(self, _request):
        await asyncio.sleep(0.05)
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_service_returns_validated_recommendation():
    outcome = RecommendationOutcome(recommendation_fixture())
    result = await RecommendationService(FakeEngine(outcome)).recommend(request_fixture())
    assert isinstance(result, ValidatedRecommendation)
    assert result.requires_user_approval is True


@pytest.mark.asyncio
async def test_service_rejects_untyped_output():
    result = await RecommendationService(FakeEngine({"outcome": "made-up"})).recommend(request_fixture())
    assert isinstance(result, RecommendationOutcome)
    assert result.root.outcome == "MODEL_ERROR"
    assert result.root.error_code == "INVALID_OUTPUT"


@pytest.mark.asyncio
async def test_service_times_out_fail_closed():
    result = await RecommendationService(SlowEngine(), timeout_seconds=0.001).recommend(request_fixture())
    assert isinstance(result, RecommendationOutcome)
    assert result.root.outcome == "MODEL_ERROR"
    assert result.root.error_code == "TIMEOUT"
