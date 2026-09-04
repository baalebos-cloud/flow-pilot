from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.database import get_engine, reset_engine_for_tests
from app.models import Base


def test_complete_demo_flow(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        config.settings, "database_url", f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    )
    reset_engine_for_tests()
    Base.metadata.create_all(get_engine())
    from app.main import app

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "sarah@example.com",
                "first_name": "Sarah",
                "last_name": "Johnson",
                "password": "strong-password",
                "phone_number": "+2348012345678",
            },
        )
        assert registration.status_code == 201
        body = registration.json()
        assert body["user"]["bmoni_user_id"].startswith("bm_usr_")
        headers = {"Authorization": f"Bearer {body['access_token']}"}

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        ai_response = client.post(
            "/v1/ai/recommend",
            headers=headers,
            json={"message": "Create a food pocket for me"},
        )
        assert ai_response.status_code == 200
        assert ai_response.json()["outcome"] == "MODEL_ERROR"
        assert ai_response.json()["error_code"] == "PROVIDER_UNAVAILABLE"

        wallet = client.post(
            "/v1/wallets/link",
            headers=headers,
            json={"wallet_address": "0x1234567890abcdef", "currency": "CNGN"},
        )
        assert wallet.status_code == 201

        plan = client.post(
            "/v1/action-plans",
            headers=headers,
            json={
                "message": "Move money to my bank",
                "amount_minor": 10_000_000,
                "currency": "CNGN",
                "recipient_name": "Demo Bank 4821",
                "available_balance_minor": 30_000_000,
            },
        )
        assert plan.status_code == 201
        assert plan.json()["expected_balance_minor"] == 20_000_000

        approval = client.post(
            f"/v1/action-plans/{plan.json()['id']}/approve",
            headers={**headers, "Idempotency-Key": "demo-request-001"},
        )
        assert approval.status_code == 201
        transaction_id = approval.json()["id"]

        signing = client.get(
            f"/v1/transactions/{transaction_id}/signing-payload", headers=headers
        )
        assert signing.status_code == 200
        assert len(signing.json()["hash"]) == 66

        submitted = client.post(
            f"/v1/transactions/{transaction_id}/signature",
            headers=headers,
            json={"signature": "0xdeadbeef1234567890"},
        )
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "COMPLETED"

        pocket = client.post(
            "/v1/pockets",
            headers=headers,
            json={"name": "Savings", "purpose": "Long-term savings", "allocated_minor": 20_000_000,
                  "currency": "CNGN", "protected": False},
        )
        assert pocket.status_code == 201

        recommendation = client.post(
            "/v1/recommendations/currency-shield",
            headers=headers,
            json={"pocket_id": pocket.json()["id"], "target_currency": "USD",
                  "amount_minor": 5_000_000, "observed_change_bps": -600,
                  "observation_window_days": 30},
        )
        assert recommendation.status_code == 201
        assert recommendation.json()["requires_user_approval"] is True

        conversion = client.post(
            f"/v1/recommendations/{recommendation.json()['id']}/approve",
            headers={**headers, "Idempotency-Key": "fx-demo-request-001"},
        )
        assert conversion.status_code == 201
        assert conversion.json()["status"] == "COMPLETED"

    get_engine().dispose()
    reset_engine_for_tests()
