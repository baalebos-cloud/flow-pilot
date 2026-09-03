import httpx
import pytest

from app import config
from app.bmoni import BmoniError, BmoniGateway


def response(status_code: int, body: dict) -> httpx.Response:
    request = httpx.Request("POST", "https://embedded-dev.bmoni.com/v1/users")
    return httpx.Response(status_code, json=body, request=request)


def test_sandbox_user_creation_uses_confirmed_contract(monkeypatch):
    monkeypatch.setattr(config.settings, "bmoni_base_url", "https://embedded-dev.bmoni.com")
    monkeypatch.setattr(config.settings, "bmoni_api_key", "test-key")
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return response(
            201,
            {"user": {"bmoniUserId": "bmoni-user-1"}},
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    gateway = BmoniGateway(mode="sandbox")

    result = gateway.create_user(
        external_id="usr_1",
        email="sarah@example.com",
        first_name="Sarah",
        last_name="Johnson",
        phone_number="+2348012345678",
    )

    assert result == {"id": "bmoni-user-1", "status": "ACTIVE"}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://embedded-dev.bmoni.com/v1/users"
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["json"] == {
        "identityId": "usr_1",
        "firstName": "Sarah",
        "lastName": "Johnson",
        "email": "sarah@example.com",
        "phoneNumber": "+2348012345678",
    }


def test_conflict_recovers_existing_partner_user(monkeypatch):
    monkeypatch.setattr(config.settings, "bmoni_base_url", "https://embedded-dev.bmoni.com")
    monkeypatch.setattr(config.settings, "bmoni_api_key", "test-key")
    replies = iter(
        [
            response(409, {"message": "email already exists"}),
            response(
                200,
                {
                    "users": [
                        {
                            "identityId": "usr_1",
                            "email": "sarah@example.com",
                            "bmoniUserId": "bmoni-existing",
                        }
                    ]
                },
            ),
        ]
    )
    monkeypatch.setattr(httpx, "request", lambda *args, **kwargs: next(replies))

    result = BmoniGateway(mode="sandbox").create_user(
        external_id="usr_1",
        email="sarah@example.com",
        first_name="Sarah",
        last_name="Johnson",
        phone_number="+2348012345678",
    )

    assert result["id"] == "bmoni-existing"


def test_sandbox_requires_credentials(monkeypatch):
    monkeypatch.setattr(config.settings, "bmoni_api_key", "")
    gateway = BmoniGateway(mode="sandbox")

    with pytest.raises(BmoniError) as exc_info:
        gateway.create_user(
            external_id="usr_1",
            email="sarah@example.com",
            first_name="Sarah",
            last_name="Johnson",
            phone_number="+2348012345678",
        )

    assert exc_info.value.code == "BMONI_NOT_CONFIGURED"


def test_owner_proof_challenge_uses_confirmed_contract(monkeypatch):
    monkeypatch.setattr(config.settings, "bmoni_base_url", "https://embedded-dev.bmoni.com")
    monkeypatch.setattr(config.settings, "bmoni_api_key", "test-key")
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return response(
            201,
            {
                "challengeId": "challenge-1",
                "groupId": "group-1",
                "message": "Sign this exact message",
                "expiresAt": "2026-09-04T12:10:00.000Z",
            },
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    result = BmoniGateway(mode="sandbox").create_owner_proof_challenge(
        bmoni_user_id="user-1",
        owner_address="0x1111111111111111111111111111111111111111",
        currency="CNGN",
    )

    assert result["challengeId"] == "challenge-1"
    assert captured["url"].endswith(
        "/v1/users/user-1/smart-wallets/owner-proof-challenges"
    )
    assert captured["json"] == {
        "currency": "CNGN",
        "userOwnerAddress": "0x1111111111111111111111111111111111111111",
    }


def test_managed_wallet_reads_before_create(monkeypatch):
    monkeypatch.setattr(config.settings, "bmoni_base_url", "https://embedded-dev.bmoni.com")
    monkeypatch.setattr(config.settings, "bmoni_api_key", "test-key")
    replies = iter(
        [
            response(200, []),
            response(
                201,
                {
                    "id": "wallet-1",
                    "currency": "CNGN",
                    "walletAddress": "0x2222222222222222222222222222222222222222",
                    "isActive": True,
                },
            ),
        ]
    )
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return next(replies)

    monkeypatch.setattr(httpx, "request", fake_request)
    result = BmoniGateway(mode="sandbox").create_managed_wallet(
        bmoni_user_id="user-1",
        owner_address="0x1111111111111111111111111111111111111111",
        currency="CNGN",
        challenge_id="challenge-1",
        signature="0x" + "a" * 130,
    )

    assert result["id"] == "wallet-1"
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    assert calls[1][2]["json"]["ownerProofChallengeId"] == "challenge-1"


def test_managed_wallet_returns_existing_currency_without_duplicate(monkeypatch):
    monkeypatch.setattr(config.settings, "bmoni_base_url", "https://embedded-dev.bmoni.com")
    monkeypatch.setattr(config.settings, "bmoni_api_key", "test-key")
    existing = {
        "id": "wallet-existing",
        "currency": "CNGN",
        "walletAddress": "0x2222222222222222222222222222222222222222",
        "isActive": True,
    }
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(method)
        return response(200, [existing])

    monkeypatch.setattr(httpx, "request", fake_request)
    result = BmoniGateway(mode="sandbox").create_managed_wallet(
        bmoni_user_id="user-1",
        owner_address="0x1111111111111111111111111111111111111111",
        currency="CNGN",
        challenge_id="challenge-1",
        signature="0x" + "a" * 130,
    )

    assert result == existing
    assert calls == ["GET"]
