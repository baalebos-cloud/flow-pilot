import asyncio

from app.ai.contracts import (
    RecommendationRequest,
    RecommendationContext,
    RecommendationType,
    RecipientContext,
    RecipientType,
)
from app.ai.engine import Member3Engine


class FakeAdapter:
    def __init__(self, response: str):
        self.response = response

    def generate_recommendation(self, request):
        return self.response


def make_request():
    return RecommendationRequest(
        request_id="req_test_001",
        user_message="Send 50000 naira to John",
        context=RecommendationContext(
            base_currency="NGN",
            recipients=[
                RecipientContext(
                    reference_id="recipient_john",
                    type=RecipientType.SAVED_WALLET,
                    display_name="John",
                    currency="NGN",
                )
            ],
            allowed_recommendation_types={
                RecommendationType.TRANSFER,
            },
        ),
    )


def run_engine(response):
    engine = Member3Engine(
        adapter=FakeAdapter(response)
    )

    return asyncio.run(
        engine.recommend(make_request())
    )


def test_valid_recommendation():
    response = """
    {
        "outcome": "RECOMMENDATION",
        "schema_version": "1.0",
        "request_id": "req_test_001",
        "recommendation_type": "TRANSFER",
        "parameters": {
            "kind": "TRANSFER",
            "amount_minor": 50000,
            "currency": "NGN",
            "recipient_reference_id": "recipient_john"
        },
        "reason_codes": [
            "USER_REQUESTED_TRANSFER"
        ],
        "evidence_reference_ids": [],
        "confidence_bps": 9500,
        "explanation": "Transfer 50000 NGN to John.",
        "requires_user_approval": true,
        "model_metadata": {
            "provider": "fake",
            "model": "test-model",
            "prompt_version": "member3-v1"
        }
    }
    """

    result = run_engine(response)

    assert result.root.outcome == "RECOMMENDATION"
    assert result.root.request_id == "req_test_001"


def test_unknown_recipient_is_rejected():
    response = """
    {
        "outcome": "RECOMMENDATION",
        "schema_version": "1.0",
        "request_id": "req_test_001",
        "recommendation_type": "TRANSFER",
        "parameters": {
            "kind": "TRANSFER",
            "amount_minor": 50000,
            "currency": "NGN",
            "recipient_reference_id": "recipient_unknown"
        },
        "reason_codes": [
            "USER_REQUESTED_TRANSFER"
        ],
        "evidence_reference_ids": [],
        "confidence_bps": 9500,
        "explanation": "Transfer 50000 NGN.",
        "requires_user_approval": true,
        "model_metadata": {
            "provider": "fake",
            "model": "test-model",
            "prompt_version": "member3-v1"
        }
    }
    """

    result = run_engine(response)

    assert result.root.outcome == "MODEL_ERROR"
    assert result.root.error_code == "INVALID_OUTPUT"


def test_wrong_request_id_is_rejected():
    response = """
    {
        "outcome": "RECOMMENDATION",
        "schema_version": "1.0",
        "request_id": "wrong_request_id",
        "recommendation_type": "TRANSFER",
        "parameters": {
            "kind": "TRANSFER",
            "amount_minor": 50000,
            "currency": "NGN",
            "recipient_reference_id": "recipient_john"
        },
        "reason_codes": [
            "USER_REQUESTED_TRANSFER"
        ],
        "evidence_reference_ids": [],
        "confidence_bps": 9500,
        "explanation": "Transfer 50000 NGN to John.",
        "requires_user_approval": true,
        "model_metadata": {
            "provider": "fake",
            "model": "test-model",
            "prompt_version": "member3-v1"
        }
    }
    """

    result = run_engine(response)

    assert result.root.outcome == "MODEL_ERROR"
    assert result.root.error_code == "INVALID_OUTPUT"


def test_invalid_json_fails_closed():
    result = run_engine("this is not json")

    assert result.root.outcome == "MODEL_ERROR"
    assert result.root.error_code == "INVALID_OUTPUT"


def test_disallowed_recommendation_type_is_rejected():
    response = """
    {
        "outcome": "RECOMMENDATION",
        "schema_version": "1.0",
        "request_id": "req_test_001",
        "recommendation_type": "BANK_WITHDRAWAL",
        "parameters": {
            "kind": "BANK_WITHDRAWAL",
            "amount_minor": 50000,
            "currency": "NGN",
            "recipient_reference_id": "recipient_john"
        },
        "reason_codes": [
            "USER_REQUESTED_WITHDRAWAL"
        ],
        "evidence_reference_ids": [],
        "confidence_bps": 9500,
        "explanation": "Withdraw 50000 NGN.",
        "requires_user_approval": true,
        "model_metadata": {
            "provider": "fake",
            "model": "test-model",
            "prompt_version": "member3-v1"
        }
    }
    """

    result = run_engine(response)

    assert result.root.outcome == "MODEL_ERROR"
    assert result.root.error_code == "INVALID_OUTPUT"


def test_recommendation_type_and_parameters_kind_must_match():
    response = """
    {
        "outcome": "RECOMMENDATION",
        "schema_version": "1.0",
        "request_id": "req_test_001",
        "recommendation_type": "TRANSFER",
        "parameters": {
            "kind": "BANK_WITHDRAWAL",
            "amount_minor": 50000,
            "currency": "NGN",
            "recipient_reference_id": "recipient_john"
        },
        "reason_codes": [
            "USER_REQUESTED_TRANSFER"
        ],
        "evidence_reference_ids": [],
        "confidence_bps": 9500,
        "explanation": "Transfer 50000 NGN.",
        "requires_user_approval": true,
        "model_metadata": {
            "provider": "fake",
            "model": "test-model",
            "prompt_version": "member3-v1"
        }
    }
    """

    result = run_engine(response)

    assert result.root.outcome == "MODEL_ERROR"
    assert result.root.error_code == "INVALID_OUTPUT"
