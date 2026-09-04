import hashlib
import hmac
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.bmoni import BmoniError
from app.main import handle_bmoni_error
from app.rate_limit import SlidingWindowRateLimiter
from app.workflow import (
    ACTION_PLAN_TRANSITIONS,
    ActionPlanStatus,
    InvalidStateTransition,
    transition,
)


@pytest.mark.asyncio
async def test_bmoni_error_handler_preserves_safe_status_mapping():
    response = await handle_bmoni_error(
        None,
        BmoniError(
            "Invalid sandbox request",
            code="BMONI_HTTP_400",
            status_code=422,
        ),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bmoni_error_handler_maps_retryable_failures_to_unavailable():
    response = await handle_bmoni_error(
        None,
        BmoniError(
            "Vendor throttled the request",
            code="BMONI_HTTP_429",
            status_code=502,
            retryable=True,
        ),
    )

    assert response.status_code == 503


def test_state_machine_allows_only_declared_transitions():
    assert transition(
        ActionPlanStatus.AWAITING_USER_APPROVAL,
        ActionPlanStatus.CREATING_PROPOSAL,
        ACTION_PLAN_TRANSITIONS,
    ) == ActionPlanStatus.CREATING_PROPOSAL

    with pytest.raises(InvalidStateTransition):
        transition(
            ActionPlanStatus.AWAITING_USER_APPROVAL,
            ActionPlanStatus.APPROVED,
            ACTION_PLAN_TRANSITIONS,
        )


def test_rate_limiter_fails_closed_and_sets_retry_after():
    now = [100.0]
    limiter = SlidingWindowRateLimiter(clock=lambda: now[0])
    limiter.check("login:127.0.0.1", limit=2, window_seconds=60)
    limiter.check("login:127.0.0.1", limit=2, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("login:127.0.0.1", limit=2, window_seconds=60)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "61"}

    now[0] = 161.0
    limiter.check("login:127.0.0.1", limit=2, window_seconds=60)


def signed_webhook_headers(secret: str, raw: bytes, event_id: str) -> dict[str, str]:
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return {
        "X-Webhook-Id": event_id,
        "X-Webhook-Signature": signature,
        "Content-Type": "application/json",
    }


def test_webhook_rejects_forged_signature(monkeypatch):
    from app import config
    from app.main import app

    monkeypatch.setattr(config.settings, "bmoni_webhook_secret", "test-secret")
    raw = b'{"id":"evt_1","eventType":"employee.withdrawal.completed","payload":{}}'
    headers = signed_webhook_headers("wrong-secret", raw, "evt_1")

    with TestClient(app) as client:
        response = client.post("/v1/webhooks/bmoni", content=raw, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook signature"


def test_webhook_rejects_mismatched_header_and_body_id(monkeypatch):
    from app import config
    from app.main import app

    monkeypatch.setattr(config.settings, "bmoni_webhook_secret", "test-secret")
    raw = b'{"id":"evt_body","eventType":"employee.withdrawal.completed","payload":{}}'
    headers = signed_webhook_headers("test-secret", raw, "evt_other")

    with TestClient(app) as client:
        response = client.post("/v1/webhooks/bmoni", content=raw, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"] == "Webhook ID header does not match body"


def test_webhook_accepts_official_shape_and_deduplicates(
    tmp_path: Path, monkeypatch
):
    from app import config
    from app.database import get_engine, reset_engine_for_tests
    from app.main import app
    from app.models import Base

    monkeypatch.setattr(
        config.settings,
        "database_url",
        f"sqlite+pysqlite:///{tmp_path / 'webhook.db'}",
    )
    monkeypatch.setattr(config.settings, "bmoni_webhook_secret", "test-secret")
    reset_engine_for_tests()
    Base.metadata.create_all(get_engine())
    raw = b'{"id":"evt_2","eventType":"employee.withdrawal.completed","payload":{"userId":"bm_usr_1"},"timestamp":"2026-08-07T12:00:00.000Z"}'
    headers = signed_webhook_headers("test-secret", raw, "evt_2")

    with TestClient(app) as client:
        first = client.post("/v1/webhooks/bmoni", content=raw, headers=headers)
        duplicate = client.post("/v1/webhooks/bmoni", content=raw, headers=headers)

    assert first.status_code == 200
    assert first.json() == {"received": True, "duplicate": False}
    assert duplicate.status_code == 200
    assert duplicate.json() == {"received": True, "duplicate": True}
    get_engine().dispose()
    reset_engine_for_tests()
