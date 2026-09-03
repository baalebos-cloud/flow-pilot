from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.ai.contracts import (
    CurrencyProtectionParameters,
    MarketObservation,
    ModelMetadata,
    PocketContext,
    RecommendationContext,
    RecommendationRequest,
    RecommendationResult,
    RecommendationType,
)
from app.ai.policy import ContractPolicyError, validate_recommendation


def request_fixture(*, protected: bool = False) -> RecommendationRequest:
    return RecommendationRequest(
        request_id="req_123",
        user_message="Protect some of my savings",
        context=RecommendationContext(
            base_currency="CNGN",
            pockets=[
                PocketContext(
                    reference_id="pocket_123",
                    purpose="SAVINGS",
                    currency="CNGN",
                    available_minor=20_000_000,
                    protected=protected,
                )
            ],
            market_observations=[
                MarketObservation(
                    reference_id="market_123",
                    source="verified-market-provider",
                    source_currency="CNGN",
                    target_currency="USD",
                    change_bps=-600,
                    window_days=30,
                    observed_at=datetime.now(timezone.utc),
                )
            ],
            allowed_recommendation_types={RecommendationType.CURRENCY_PROTECTION},
        ),
    )


def recommendation_fixture(**changes) -> RecommendationResult:
    values = {
        "outcome": "RECOMMENDATION",
        "request_id": "req_123",
        "recommendation_type": "CURRENCY_PROTECTION",
        "parameters": CurrencyProtectionParameters(
            kind="CURRENCY_PROTECTION",
            pocket_reference_id="pocket_123",
            market_observation_reference_id="market_123",
            suggested_amount_minor=4_000_000,
            source_currency="CNGN",
            target_currency="USD",
        ),
        "reason_codes": ["CURRENCY_DECLINE_THRESHOLD_REACHED"],
        "evidence_reference_ids": ["market_123"],
        "confidence_bps": 9200,
        "explanation": "Consider diversifying part of the savings pocket.",
        "requires_user_approval": False,
        "model_metadata": ModelMetadata(provider="test", model="fake", prompt_version="1"),
    }
    values.update(changes)
    return RecommendationResult(**values)


def test_backend_derives_approval_even_when_ai_says_false():
    validated = validate_recommendation(request_fixture(), recommendation_fixture())
    assert validated.requires_user_approval is True


def test_unknown_ai_reference_fails_closed():
    recommendation = recommendation_fixture(
        parameters=CurrencyProtectionParameters(
            kind="CURRENCY_PROTECTION",
            pocket_reference_id="invented_pocket",
            market_observation_reference_id="market_123",
            suggested_amount_minor=4_000_000,
            source_currency="CNGN",
            target_currency="USD",
        )
    )
    with pytest.raises(ContractPolicyError, match="unknown pocket"):
        validate_recommendation(request_fixture(), recommendation)


def test_protected_pocket_fails_closed():
    with pytest.raises(ContractPolicyError, match="Protected pockets"):
        validate_recommendation(request_fixture(protected=True), recommendation_fixture())


def test_contract_rejects_unexpected_fields():
    payload = request_fixture().model_dump(mode="json")
    payload["secret"] = "must-not-be-accepted"
    with pytest.raises(ValidationError, match="Extra inputs"):
        RecommendationRequest.model_validate(payload)

