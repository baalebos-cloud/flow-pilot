from pathlib import Path

import pytest

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config
from app.database import get_engine, reset_engine_for_tests, session_scope
from app.main import app, validate_pocket_allocation
from app.models import Base, Pocket, User
from app.repositories import utc_now


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch):
    """Configure a fresh SQLite database for each isolated test."""

    # Point SQLAlchemy at a temporary SQLite database for this test.
    monkeypatch.setattr(
        config.settings,
        "database_url",
        f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
    )

    # Clear any previously cached engine before creating the test database.
    reset_engine_for_tests()

    # Create the SQLAlchemy tables required by the test.
    Base.metadata.create_all(get_engine())

    yield

    # Release the test database connection and reset the cached engine.
    get_engine().dispose()
    reset_engine_for_tests()


def test_complete_demo_flow(
    isolated_db,
    monkeypatch,
):
    """Exercise the main registration, wallet, transaction, pocket, and FX flow."""

    # Keep pocket allocation tests independent of the live balance service.
    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        # Register a user using the current authentication contract.
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

        headers = {
            "Authorization": f"Bearer {body['access_token']}",
        }

        # Verify the AI endpoint gracefully reports unavailable providers.
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        ai_response = client.post(
            "/v1/ai/recommend",
            headers=headers,
            json={
                "message": "Create a food pocket for me",
            },
        )

        assert ai_response.status_code == 200
        assert ai_response.json()["outcome"] == "MODEL_ERROR"
        assert ai_response.json()["error_code"] == "PROVIDER_UNAVAILABLE"

        # Link the user's wallet.
        wallet = client.post(
            "/v1/wallets/link",
            headers=headers,
            json={
                "wallet_address": "0x1234567890abcdef",
                "currency": "CNGN",
            },
        )

        assert wallet.status_code == 201

        # Create an action plan.
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

        # Approve the action plan and create the BMONI proposal.
        approval = client.post(
            f"/v1/action-plans/{plan.json()['id']}/approve",
            headers={
                **headers,
                "Idempotency-Key": "demo-request-001",
            },
        )

        assert approval.status_code == 201

        transaction_id = approval.json()["id"]

        # Retrieve the transaction signing payload.
        signing = client.get(
            f"/v1/transactions/{transaction_id}/signing-payload",
            headers=headers,
        )

        assert signing.status_code == 200
        assert len(signing.json()["hash"]) == 66

        # Submit the transaction signature.
        submitted = client.post(
            f"/v1/transactions/{transaction_id}/signature",
            headers=headers,
            json={
                "signature": "0xdeadbeef1234567890",
            },
        )

        assert submitted.status_code == 200
        assert submitted.json()["status"] == "COMPLETED"

        # Create a pocket using the authoritative-balance test provider.
        pocket = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Savings",
                "purpose": "Long-term savings",
                "allocated_minor": 20_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        assert pocket.status_code == 201

        # Create a Currency Shield recommendation.
        recommendation = client.post(
            "/v1/recommendations/currency-shield",
            headers=headers,
            json={
                "pocket_id": pocket.json()["id"],
                "target_currency": "USD",
                "amount_minor": 5_000_000,
                "observed_change_bps": -600,
                "observation_window_days": 30,
            },
        )

        assert recommendation.status_code == 201
        assert recommendation.json()["requires_user_approval"] is True

        # Approval creates a proposal that still requires a user signature.
        conversion = client.post(
            f"/v1/recommendations/{recommendation.json()['id']}/approve",
            headers={
                **headers,
                "Idempotency-Key": "fx-demo-request-001",
            },
        )

        assert conversion.status_code == 201
        assert conversion.json()["status"] == "PENDING_SIGNATURE"
        assert conversion.json()["money_has_moved"] is False

        # Retrieve the Currency Shield signing payload.
        fx_signing = client.get(
            f"/v1/fx/conversions/{conversion.json()['id']}/signing-payload",
            headers=headers,
        )

        assert fx_signing.status_code == 200
        assert len(fx_signing.json()["hashToSign"]) == 66

        # Submit the required Currency Shield signature.
        fx_submitted = client.post(
            f"/v1/fx/conversions/{conversion.json()['id']}/signature",
            headers=headers,
            json={
                "signature": "0x" + "a" * 130,
            },
        )

        assert fx_submitted.status_code == 200
        assert fx_submitted.json()["status"] == "COMPLETED"
        assert fx_submitted.json()["money_has_moved"] is True


def test_pocket_allocation_exceeds_authoritative_balance(
    isolated_db,
):
    """Reject a new pocket when aggregate allocation exceeds the wallet balance."""

    # Create the parent user required by the pocket foreign key.
    with session_scope() as session:
        session.add(
            User(
                id="usr_test",
                email="pocket-test@example.com",
                name="Pocket Test User",
                password_hash="test-password-hash",
                bmoni_user_id="bm_test_user",
                provisioning_status="ACTIVE",
                created_at=utc_now(),
            )
        )

    # Create an existing pocket allocation that consumes most of the balance.
    with session_scope() as session:
        session.add(
            Pocket(
                id="pkt_existing",
                user_id="usr_test",
                name="Savings",
                purpose="Emergency savings",
                allocated_minor=80_000_000,
                spent_minor=0,
                currency="CNGN",
                protected=False,
                created_at=utc_now(),
            )
        )

    with session_scope() as session:
        user = session.scalar(
            select(User).where(User.id == "usr_test")
        )

        assert user is not None

        with pytest.raises(HTTPException) as exc_info:
            validate_pocket_allocation(
                session=session,
                user_id=user.id,
                currency="CNGN",
                requested_allocation_minor=30_000_000,
                wallet_balance_minor=100_000_000,
            )

        assert exc_info.value.status_code == 422
        assert (
            exc_info.value.detail["code"]
            == "POCKET_ALLOCATION_EXCEEDS_BALANCE"
        )


def test_pocket_allocation_is_calculated_per_currency(
    isolated_db,
):
    """Allow an allocation when another currency does not consume its balance."""

    # Create the test user.
    with session_scope() as session:
        session.add(
            User(
                id="usr_test",
                email="currency-test@example.com",
                name="Currency Test User",
                password_hash="test-password-hash",
                bmoni_user_id="bm_currency_test",
                provisioning_status="ACTIVE",
                created_at=utc_now(),
            )
        )

    # Create a CNGN allocation.
    with session_scope() as session:
        session.add(
            Pocket(
                id="pkt_cngn",
                user_id="usr_test",
                name="CNGN Savings",
                purpose="CNGN savings",
                allocated_minor=90_000_000,
                spent_minor=0,
                currency="CNGN",
                protected=False,
                created_at=utc_now(),
            )
        )

    # USD allocation must be calculated independently from CNGN.
    with session_scope() as session:
        user = session.scalar(
            select(User).where(User.id == "usr_test")
        )

        assert user is not None

        validate_pocket_allocation(
            session=session,
            user_id=user.id,
            currency="USD",
            requested_allocation_minor=50_000_000,
            wallet_balance_minor=100_000_000,
        )


def test_create_pocket_rejects_allocation_above_balance(
    isolated_db,
    monkeypatch,
):
    """Return the required API error for an excessive aggregate allocation."""

    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "allocation@example.com",
                "first_name": "Allocation",
                "last_name": "Test",
                "password": "strong-password",
                "phone_number": "+2348012345678",
            },
        )

        assert registration.status_code == 201

        token = registration.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
        }

        first_pocket = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Existing Savings",
                "purpose": "Existing allocation",
                "allocated_minor": 80_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        assert first_pocket.status_code == 201

        second_pocket = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "New Savings",
                "purpose": "Excess allocation",
                "allocated_minor": 30_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        assert second_pocket.status_code == 422
        assert (
            second_pocket.json()["detail"]["code"]
            == "POCKET_ALLOCATION_EXCEEDS_BALANCE"
        )


def test_pocket_transfer_updates_allocations(
    isolated_db,
    monkeypatch,
):
    """Transfer available allocation from one pocket to another."""

    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "transfer@example.com",
                "first_name": "Transfer",
                "last_name": "Test",
                "password": "strong-password",
                "phone_number": "+2348012345678",
            },
        )

        assert registration.status_code == 201

        token = registration.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
        }

        source = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Savings",
                "purpose": "Savings",
                "allocated_minor": 40_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        destination = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Bills",
                "purpose": "Bills",
                "allocated_minor": 10_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        assert source.status_code == 201
        assert destination.status_code == 201

        transfer = client.post(
            "/v1/pockets/transfer",
            headers=headers,
            json={
                "source_pocket_id": source.json()["id"],
                "destination_pocket_id": destination.json()["id"],
                "amount_minor": 15_000_000,
            },
        )

        assert transfer.status_code == 200

        result = transfer.json()

        assert result["source"]["allocated_minor"] == 25_000_000
        assert result["destination"]["allocated_minor"] == 25_000_000


def test_pocket_transfer_rejects_insufficient_balance(
    isolated_db,
    monkeypatch,
):
    """Reject transfers larger than the source pocket's available balance."""

    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "transfer-insufficient@example.com",
                "first_name": "Transfer",
                "last_name": "Test",
                "password": "strong-password",
                "phone_number": "+2348012345679",
            },
        )

        assert registration.status_code == 201

        token = registration.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
        }

        source = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Savings",
                "purpose": "Savings",
                "allocated_minor": 10_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        destination = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Bills",
                "purpose": "Bills",
                "allocated_minor": 5_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        assert source.status_code == 201
        assert destination.status_code == 201

        transfer = client.post(
            "/v1/pockets/transfer",
            headers=headers,
            json={
                "source_pocket_id": source.json()["id"],
                "destination_pocket_id": destination.json()["id"],
                "amount_minor": 20_000_000,
            },
        )

        assert transfer.status_code == 422
        assert (
            transfer.json()["detail"]["code"]
            == "INSUFFICIENT_POCKET_BALANCE"
        )


def test_pocket_transfer_rejects_currency_mismatch(
    isolated_db,
    monkeypatch,
):
    """Reject transfers between pockets with different currencies."""

    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "transfer-currency@example.com",
                "first_name": "Currency",
                "last_name": "Transfer",
                "password": "strong-password",
                "phone_number": "+2348012345680",
            },
        )

        assert registration.status_code == 201

        token = registration.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
        }

        source = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Naira",
                "purpose": "Naira funds",
                "allocated_minor": 10_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        destination = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Dollar",
                "purpose": "Dollar funds",
                "allocated_minor": 5_000_000,
                "currency": "USD",
                "protected": False,
            },
        )

        assert source.status_code == 201
        assert destination.status_code == 201

        transfer = client.post(
            "/v1/pockets/transfer",
            headers=headers,
            json={
                "source_pocket_id": source.json()["id"],
                "destination_pocket_id": destination.json()["id"],
                "amount_minor": 1_000_000,
            },
        )

        assert transfer.status_code == 422
        assert transfer.json()["detail"]["code"] == "CURRENCY_MISMATCH"


def test_duplicate_pocket_name_is_rejected(
    isolated_db,
    monkeypatch,
):
    """Reject two pockets with the same name for one user."""

    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "duplicate@example.com",
                "first_name": "Duplicate",
                "last_name": "User",
                "password": "password123",
                "phone_number": "+2348012345678",
            },
        )

        assert registration.status_code == 201

        token = registration.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
        }

        first = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Savings",
                "purpose": "Emergency savings",
                "allocated_minor": 1_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        assert first.status_code == 201

        duplicate = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Savings",
                "purpose": "Another savings pocket",
                "allocated_minor": 500_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        assert duplicate.status_code == 409


def test_cross_user_pocket_access_is_rejected(
    isolated_db,
    monkeypatch,
):
    """Reject access to a pocket owned by another user."""

    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        first_register = client.post(
            "/v1/auth/register",
            json={
                "email": "owner@example.com",
                "first_name": "Pocket",
                "last_name": "Owner",
                "password": "password123",
                "phone_number": "+2348012345678",
            },
        )

        second_register = client.post(
            "/v1/auth/register",
            json={
                "email": "attacker@example.com",
                "first_name": "Other",
                "last_name": "User",
                "password": "password123",
                "phone_number": "+2348087654321",
            },
        )

        assert first_register.status_code == 201
        assert second_register.status_code == 201

        first_headers = {
            "Authorization": (
                f"Bearer {first_register.json()['access_token']}"
            ),
        }

        second_headers = {
            "Authorization": (
                f"Bearer {second_register.json()['access_token']}"
            ),
        }

        pocket = client.post(
            "/v1/pockets",
            headers=first_headers,
            json={
                "name": "Private Savings",
                "purpose": "Private funds",
                "allocated_minor": 1_000_000,
                "currency": "CNGN",
                "protected": False,
            },
        )

        assert pocket.status_code == 201

        response = client.get(
            f"/v1/pockets/{pocket.json()['id']}",
            headers=second_headers,
        )

        assert response.status_code == 404


def test_pocket_rejects_unsupported_currency(
    isolated_db,
    monkeypatch,
):
    """Reject pocket creation for unsupported currencies."""

    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "currency@example.com",
                "first_name": "Currency",
                "last_name": "User",
                "password": "password123",
                "phone_number": "+2348012345678",
            },
        )

        assert registration.status_code == 201

        token = registration.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
        }

        response = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Euro Pocket",
                "purpose": "Unsupported currency test",
                "allocated_minor": 1_000_000,
                "currency": "EUR",
                "protected": False,
            },
        )

        assert response.status_code == 422


def test_protected_pocket_cannot_fund_currency_shield(
    isolated_db,
    monkeypatch,
):
    """Reject Currency Shield recommendations from protected pockets."""

    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "protected@example.com",
                "first_name": "Protected",
                "last_name": "User",
                "password": "password123",
                "phone_number": "+2348012345678",
            },
        )

        assert registration.status_code == 201

        token = registration.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
        }

        pocket = client.post(
            "/v1/pockets",
            headers=headers,
            json={
                "name": "Protected Savings",
                "purpose": "Funds that must not be converted",
                "allocated_minor": 5_000_000,
                "currency": "CNGN",
                "protected": True,
            },
        )

        assert pocket.status_code == 201

        response = client.post(
            "/v1/recommendations/currency-shield",
            headers=headers,
            json={
                "pocket_id": pocket.json()["id"],
                "target_currency": "USD",
                "amount_minor": 1_000_000,
                "observed_change_bps": -600,
                "observation_window_days": 30,
            },
        )

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "PROTECTED_POCKET"