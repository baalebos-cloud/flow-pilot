import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.rate_limit import SlidingWindowRateLimiter
from app.workflow import (
    ACTION_PLAN_TRANSITIONS,
    ActionPlanStatus,
    InvalidStateTransition,
    transition,
)


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


def signed_webhook_headers(secret: str, raw: bytes, timestamp: int) -> dict[str, str]:
    signature = hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    return {
        "X-BMONI-Timestamp": str(timestamp),
        "X-BMONI-Signature": signature,
        "Content-Type": "application/json",
    }


def test_webhook_rejects_stale_signed_request(monkeypatch):
    from app import config
    from app.main import app

    monkeypatch.setattr(config.settings, "bmoni_webhook_secret", "test-secret")
    raw = b'{"id":"evt_old","type":"proposal.updated","proposal_id":"p1","status":"COMPLETED"}'
    headers = signed_webhook_headers("test-secret", raw, int(time.time()) - 301)

    with TestClient(app) as client:
        response = client.post("/v1/webhooks/bmoni", content=raw, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Stale webhook"
