from pathlib import Path

from app.db import connection, now_iso

from fastapi.testclient import TestClient

from app import config

import pytest

from fastapi import HTTPException

from app.db import connection, init_db, now_iso
from app.main import validate_pocket_allocation




def test_complete_demo_flow(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as client:
        # Provide the phone number required by the live BMONI sandbox during user provisioning.
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "sarah@example.com",
                "name": "Sarah",
                "password": "strong-password",
                "phone_number": "+2348012345678",
            },
        )
        assert registration.status_code == 201
        body = registration.json()
        assert body["user"]["bmoni_user_id"].startswith("bm_usr_")
        headers = {"Authorization": f"Bearer {body['access_token']}"}

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


# Give each isolated test its own temporary SQLite database.
@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Configure a fresh SQLite database for tests that work directly with the database."""

    # Point the application database setting at a temporary test database.
    monkeypatch.setattr(
        config.settings,
        "db_path",
        str(tmp_path / "test.db"),
    )

    # Create all application tables inside the temporary database.
    init_db()


# Verify that a pocket allocation is rejected when aggregate allocation exceeds the wallet balance.
def test_pocket_allocation_exceeds_authoritative_balance(isolated_db):
    """Reject a new pocket when total allocations exceed the backend wallet balance."""

    user = {"id": "usr_test"}

    # # Create the SQLite tables required by this isolated database test.
    # init_db()

    # Create the parent user required by the pocket foreign-key constraint.
    with connection() as conn:
        conn.execute(
            """
                INSERT INTO users
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "usr_test",
                "pocket-test@example.com",
                "Pocket Test User",
                "test-password-hash",
                "bm_test_user",
                now_iso(),
            ),
        )

    # Create an existing pocket allocation that consumes most of the mock balance.
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO pockets
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pkt_existing",
                user["id"],
                "Savings",
                "Emergency savings",
                80_000_000,
                0,
                "CNGN",
                0,
                now_iso(),
            ),
        )

    # The new allocation would bring the total to 110,000,000 against a 100,000,000 balance.
    with pytest.raises(HTTPException) as exc_info:
        validate_pocket_allocation(
            user=user,
            currency="CNGN",
            requested_allocation_minor=30_000_000,
            wallet_balance_minor=100_000_000,
        )

    # Confirm the API contract exposes the required rejection code.
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "POCKET_ALLOCATION_EXCEEDS_BALANCE"


# Verify that allocations are calculated independently for each supported currency.
def test_pocket_allocation_is_calculated_per_currency(isolated_db):
    """Allow an allocation when another currency's pockets do not consume its balance."""

    user = {"id": "usr_test"}

    # Create the SQLite tables required by this isolated database test.
    # init_db()

    # Create the parent user required by the pocket foreign-key constraint.
    with connection() as conn:
        conn.execute(
            """
                INSERT INTO users
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "usr_test",
                "pocket-test@example.com",
                "Pocket Test User",
                "test-password-hash",
                "bm_test_user",
                now_iso(),
            ),
        )

    # Create an existing NGN allocation that should not affect a USD allocation.
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO pockets
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pkt_cngn",
                user["id"],
                "Savings",
                "CNGN savings",
                90_000_000,
                0,
                "CNGN",
                0,
                now_iso(),
            ),
        )

    # A USD allocation is checked only against existing USD allocations.
    validate_pocket_allocation(
        user=user,
        currency="USD",
        requested_allocation_minor=50_000_000,
        wallet_balance_minor=100_000_000,
    )
# Verify that the pocket creation endpoint rejects an allocation above the authoritative balance.
def test_create_pocket_rejects_allocation_above_balance(isolated_db, monkeypatch):
    """Return the required API error when a pocket exceeds the user's wallet balance."""

    # Use a deterministic backend balance for this isolated API test.
    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    from app.main import app

    # Start the application so authentication and database initialization behave normally.
    with TestClient(app) as client:
        # Register a test user through the real API.
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "allocation@example.com",
                "name": "Allocation Test User",
                "password": "strong-password",
                "phone_number": "+2348012345678",
            },
        )

        assert registration.status_code == 201

        # Extract the authentication token for subsequent requests.
        token = registration.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create an allocation that consumes most of the authoritative balance.
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

        # Attempt to allocate another 30,000,000, which would bring the total to 110,000,000.
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

        # Confirm that the endpoint rejects the aggregate allocation.
        assert second_pocket.status_code == 422

        # Confirm that the frontend receives the agreed machine-readable error code.
        assert second_pocket.json()["detail"]["code"] == "POCKET_ALLOCATION_EXCEEDS_BALANCE"

# Verify that allocated funds can move between two pockets owned by one user.
def test_pocket_transfer_updates_allocations(isolated_db, monkeypatch):
    """Transfer available allocation from one pocket to another."""

    from fastapi.testclient import TestClient
    from app.main import app

    # Use the temporary BMONI balance provider for this API-level test.
    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    # Create an authenticated test user.
    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "transfer@example.com",
                "name": "Transfer Test User",
                "password": "strong-password",
                "phone_number": "+2348012345678",
            },
        )

        assert registration.status_code == 201
        token = registration.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create the source pocket.
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

        assert source.status_code == 201

        # Create the destination pocket.
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

        assert destination.status_code == 201

        # Transfer 15,000,000 minor units from Savings to Bills.
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

        # Confirm the source allocation decreased.
        assert result["source"]["allocated_minor"] == 25_000_000

        # Confirm the destination allocation increased.
        assert result["destination"]["allocated_minor"] == 25_000_000

# Verify that a transfer cannot exceed the source pocket's available amount.
def test_pocket_transfer_rejects_insufficient_balance(isolated_db, monkeypatch):
    """Reject transfers larger than the source pocket's available balance."""

    from fastapi.testclient import TestClient
    from app.main import app

    # Keep pocket creation independent from the real BMONI service.
    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "transfer-insufficient@example.com",
                "name": "Transfer Test User",
                "password": "strong-password",
                "phone_number": "+2348012345679",
            },
        )

        assert registration.status_code == 201
        token = registration.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

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

        # Attempt to transfer more than the source pocket contains.
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
        assert transfer.json()["detail"]["code"] == "INSUFFICIENT_POCKET_BALANCE"

# Verify that pockets using different currencies cannot be transferred between.
def test_pocket_transfer_rejects_currency_mismatch(isolated_db, monkeypatch):
    """Reject transfers between pockets with different currencies."""

    from fastapi.testclient import TestClient
    from app.main import app

    # Supply sufficient balances for both supported currencies.
    monkeypatch.setattr(
        "app.main.get_authoritative_wallet_balance",
        lambda user, currency: 100_000_000,
    )

    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "transfer-currency@example.com",
                "name": "Currency Transfer User",
                "password": "strong-password",
                "phone_number": "+2348012345680",
            },
        )

        assert registration.status_code == 201
        token = registration.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

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

        # Attempt to move funds across currencies.
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

# Verify duplicate pocket names are rejected for the same user.
def test_duplicate_pocket_name_is_rejected(tmp_path, monkeypatch):
    """Reject two pockets with the same name for one user."""

    # Use an isolated database for this API test.
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "test.db"))

    # Create the application tables before making requests.
    init_db()

    # Import the application after configuring the test database.
    from app.main import app

    # Create a client for the API.
    with TestClient(app) as client:
        # Register a test user.
        register = client.post(
            "/v1/auth/register",
            json={
                "email": "duplicate@example.com",
                "name": "Duplicate User",
                "password": "password123",
                "phone_number": "08012345678",
            },
        )
        assert register.status_code == 201

        # Log in to obtain the user's access token.
        login = client.post(
            "/v1/auth/login",
            json={
                "email": "duplicate@example.com",
                "password": "password123",
            },
        )
        assert login.status_code == 200

        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create the first pocket.
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

        # Attempt to create another pocket with the same name.
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

        # The unique user/name constraint should reject the duplicate.
        assert duplicate.status_code == 409


# Verify users cannot access another user's pocket.
def test_cross_user_pocket_access_is_rejected(tmp_path, monkeypatch):
    """Reject access to a pocket owned by another user."""

    # Use an isolated database for this API test.
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "test.db"))

    # Create the application tables.
    init_db()

    # Import the application after configuring the database.
    from app.main import app

    # Create a test client.
    with TestClient(app) as client:
        # Register the first user.
        first_register = client.post(
            "/v1/auth/register",
            json={
                "email": "owner@example.com",
                "name": "Pocket Owner",
                "password": "password123",
                "phone_number": "08012345678",
            },
        )
        assert first_register.status_code == 201

        # Register the second user.
        second_register = client.post(
            "/v1/auth/register",
            json={
                "email": "attacker@example.com",
                "name": "Other User",
                "password": "password123",
                "phone_number": "08087654321",
            },
        )
        assert second_register.status_code == 201

        # Log in as the first user.
        first_login = client.post(
            "/v1/auth/login",
            json={
                "email": "owner@example.com",
                "password": "password123",
            },
        )
        assert first_login.status_code == 200

        # Log in as the second user.
        second_login = client.post(
            "/v1/auth/login",
            json={
                "email": "attacker@example.com",
                "password": "password123",
            },
        )
        assert second_login.status_code == 200

        # Build authorization headers for both users.
        first_headers = {
            "Authorization": f"Bearer {first_login.json()['access_token']}"
        }
        second_headers = {
            "Authorization": f"Bearer {second_login.json()['access_token']}"
        }

        # Create a pocket belonging to the first user.
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

        pocket_id = pocket.json()["id"]

        # Attempt to read the first user's pocket as the second user.
        response = client.get(
            f"/v1/pockets/{pocket_id}",
            headers=second_headers,
        )

        # Ownership protection should hide the pocket.
        assert response.status_code == 404

# Verify unsupported pocket currencies are rejected.
def test_pocket_rejects_unsupported_currency(tmp_path, monkeypatch):
    """Reject pocket creation for currencies outside the supported set."""

    # Use an isolated database.
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "test.db"))

    # Create the application tables.
    init_db()

    # Import the application.
    from app.main import app

    # Create a test client.
    with TestClient(app) as client:
        # Register the test user.
        register = client.post(
            "/v1/auth/register",
            json={
                "email": "currency@example.com",
                "name": "Currency User",
                "password": "password123",
                "phone_number": "08012345678",
            },
        )
        assert register.status_code == 201

        # Log in to obtain an access token.
        login = client.post(
            "/v1/auth/login",
            json={
                "email": "currency@example.com",
                "password": "password123",
            },
        )
        assert login.status_code == 200

        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt to create a pocket using an unsupported currency.
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

        # The API should reject unsupported currencies.
        assert response.status_code == 422


# Verify protected pockets cannot fund Currency Shield.
def test_protected_pocket_cannot_fund_currency_shield(tmp_path, monkeypatch):
    """Reject Currency Shield recommendations from protected pockets."""

    # Use an isolated database.
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "test.db"))

    # Create the application tables.
    init_db()

    # Import the application.
    from app.main import app

    # Create a test client.
    with TestClient(app) as client:
        # Register the test user.
        register = client.post(
            "/v1/auth/register",
            json={
                "email": "protected@example.com",
                "name": "Protected User",
                "password": "password123",
                "phone_number": "08012345678",
            },
        )
        assert register.status_code == 201

        # Log in to obtain the access token.
        login = client.post(
            "/v1/auth/login",
            json={
                "email": "protected@example.com",
                "password": "password123",
            },
        )
        assert login.status_code == 200

        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create a protected pocket with enough funds for the requested conversion.
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

        pocket_id = pocket.json()["id"]

        # Attempt to create a Currency Shield recommendation from the protected pocket.
        response = client.post(
            "/v1/recommendations/currency-shield",
            headers=headers,
            json={
                "pocket_id": pocket_id,
                "target_currency": "USD",
                "amount_minor": 1_000_000,
                "observed_change_bps": -600,
                "observation_window_days": 30,
            },
        )

        # Protected pockets must never fund Currency Shield.
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "PROTECTED_POCKET"


def test_investment_opportunities_are_read_only(tmp_path, monkeypatch):
    """Expose verified investment opportunities without execution controls."""

    # Use an isolated database for this test.
    monkeypatch.setattr(
        config.settings,
        "db_path",
        str(tmp_path / "test.db"),
    )

    # Create the application tables.
    init_db()

    # Import the application.
    from app.main import app

    # Create a test client and trigger application startup.
    with TestClient(app) as client:
        # Register a test user.
        register = client.post(
            "/v1/auth/register",
            json={
                "email": "investor@example.com",
                "name": "Investor User",
                "password": "password123",
                "phone_number": "08012345678",
            },
        )
        assert register.status_code == 201

        # Log in to obtain the access token.
        login = client.post(
            "/v1/auth/login",
            json={
                "email": "investor@example.com",
                "password": "password123",
            },
        )
        assert login.status_code == 200

        # Build the authenticated request headers.
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Retrieve the read-only investment opportunities.
        response = client.get(
            "/v1/investment-opportunities",
            headers=headers,
        )

        # The endpoint should return the seeded opportunities.
        assert response.status_code == 200
        assert len(response.json()) >= 1

        # Verify the expected informational fields are exposed.
        opportunity = response.json()[0]
        assert "provider" in opportunity
        assert "regulatory_status" in opportunity
        assert "risk_level" in opportunity
        assert "liquidity" in opportunity
        assert "fee_minor" in opportunity

        # Investment opportunities must not expose execution controls.
        assert "execute" not in opportunity
        assert "execution_url" not in opportunity