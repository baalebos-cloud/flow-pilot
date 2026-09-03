import hashlib
import hmac
import json
import sqlite3
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.bmoni import BmoniConfigurationError, bmoni
from app.config import settings
from app.db import connection, init_db, json_text, now_iso, row_dict
from app.schemas import (
    ActionPlanRequest, CurrencyShieldRequest, LoginRequest, PocketCreateRequest,
    RegisterRequest, SignatureRequest, WalletLinkRequest,
)
from app.security import create_access_token, decode_access_token, hash_password, verify_password


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="FlowPilot API", version="0.1.0", lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    with connection() as conn:
        user = row_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


@app.exception_handler(BmoniConfigurationError)
async def bmoni_config_error(_: Request, exc: BmoniConfigurationError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "bmoni_mode": settings.bmoni_mode}


@app.post("/v1/auth/register", status_code=201)
def register(payload: RegisterRequest) -> dict:
    user_id = new_id("usr")
    with connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (str(payload.email).lower(),)).fetchone():
            raise HTTPException(status_code=409, detail="A FlowPilot account with this email already exists")
    try:
        remote = bmoni.create_user(external_id=user_id, email=str(payload.email), name=payload.name)
        with connection() as conn:
            conn.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, str(payload.email).lower(), payload.name, hash_password(payload.password), remote["id"], now_iso()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A FlowPilot account with this email already exists")
    return {
        "access_token": create_access_token(user_id),
        "token_type": "bearer",
        "user": {"id": user_id, "email": str(payload.email), "name": payload.name, "bmoni_user_id": remote["id"]},
    }


@app.post("/v1/auth/login")
def login(payload: LoginRequest) -> dict:
    with connection() as conn:
        user = row_dict(conn.execute("SELECT * FROM users WHERE email = ?", (str(payload.email).lower(),)).fetchone())
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"access_token": create_access_token(user["id"]), "token_type": "bearer"}


@app.get("/v1/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {k: user[k] for k in ("id", "email", "name", "bmoni_user_id", "created_at")}


@app.post("/v1/wallets/link", status_code=201)
def link_wallet(payload: WalletLinkRequest, user: dict = Depends(current_user)) -> dict:
    currency = payload.currency.upper()
    if currency != "CNGN":
        raise HTTPException(status_code=422, detail="The MVP currently supports CNGN only")
    remote = bmoni.link_wallet(
        bmoni_user_id=user["bmoni_user_id"], address=payload.wallet_address, currency=currency
    )
    wallet_id = new_id("wal")
    try:
        with connection() as conn:
            conn.execute(
                "INSERT INTO wallets VALUES (?, ?, ?, ?, ?, ?, ?)",
                (wallet_id, user["id"], remote["id"], payload.wallet_address, currency, remote["status"], now_iso()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="This user or wallet address is already linked")
    return {"id": wallet_id, "bmoni_wallet_id": remote["id"], "status": remote["status"], "currency": currency}


@app.post("/v1/action-plans", status_code=201)
def create_action_plan(payload: ActionPlanRequest, user: dict = Depends(current_user)) -> dict:
    currency = payload.currency.upper()
    failures = []
    if currency != "CNGN":
        failures.append("UNSUPPORTED_CURRENCY")
    if payload.amount_minor > payload.available_balance_minor:
        failures.append("INSUFFICIENT_BALANCE")
    if payload.amount_minor > settings.max_transaction_minor:
        failures.append("PER_TRANSACTION_LIMIT_EXCEEDED")
    if failures:
        raise HTTPException(status_code=422, detail={"risk_status": "REJECTED", "reasons": failures})

    plan_id = new_id("plan")
    expected = payload.available_balance_minor - payload.amount_minor
    with connection() as conn:
        conn.execute(
            "INSERT INTO action_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (plan_id, user["id"], "BANK_WITHDRAWAL", payload.amount_minor, currency,
             payload.recipient_name, payload.message, payload.available_balance_minor, expected,
             "PASSED", "AWAITING_USER_APPROVAL", now_iso()),
        )
    return {
        "id": plan_id,
        "action_type": "BANK_WITHDRAWAL",
        "amount_minor": payload.amount_minor,
        "currency": currency,
        "recipient_name": payload.recipient_name,
        "available_balance_minor": payload.available_balance_minor,
        "expected_balance_minor": expected,
        "risk_status": "PASSED",
        "approval_status": "AWAITING_USER_APPROVAL",
        "requires_user_approval": True,
        "money_has_moved": False,
    }


@app.post("/v1/action-plans/{plan_id}/approve", status_code=201)
def approve_action_plan(
    plan_id: str,
    idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
    user: dict = Depends(current_user),
) -> dict:
    with connection() as conn:
        existing = row_dict(conn.execute(
            "SELECT * FROM transactions WHERE user_id = ? AND idempotency_key = ?",
            (user["id"], idempotency_key),
        ).fetchone())
        if existing:
            return existing
        plan = row_dict(conn.execute(
            "SELECT * FROM action_plans WHERE id = ? AND user_id = ?", (plan_id, user["id"])
        ).fetchone())
        if not plan:
            raise HTTPException(status_code=404, detail="Action plan not found")
        if plan["approval_status"] != "AWAITING_USER_APPROVAL":
            raise HTTPException(status_code=409, detail="Action plan cannot be approved in its current state")
        proposal = bmoni.create_withdrawal_proposal(
            bmoni_user_id=user["bmoni_user_id"], amount_minor=plan["amount_minor"],
            currency=plan["currency"], recipient_name=plan["recipient_name"]
        )
        transaction_id = new_id("txn")
        conn.execute("UPDATE action_plans SET approval_status = 'APPROVED' WHERE id = ?", (plan_id,))
        conn.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (transaction_id, user["id"], plan_id, proposal["id"], plan["amount_minor"],
             plan["currency"], "PENDING_SIGNATURE", proposal["status"], idempotency_key, now_iso()),
        )
    return {"id": transaction_id, "bmoni_proposal_id": proposal["id"], "status": "PENDING_SIGNATURE"}


def owned_transaction(transaction_id: str, user_id: str) -> dict:
    with connection() as conn:
        transaction = row_dict(conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user_id)
        ).fetchone())
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


@app.get("/v1/transactions/{transaction_id}")
def get_transaction(transaction_id: str, user: dict = Depends(current_user)) -> dict:
    return owned_transaction(transaction_id, user["id"])


@app.get("/v1/transactions/{transaction_id}/signing-payload")
def signing_payload(transaction_id: str, user: dict = Depends(current_user)) -> dict:
    transaction = owned_transaction(transaction_id, user["id"])
    if transaction["status"] != "PENDING_SIGNATURE":
        raise HTTPException(status_code=409, detail="Transaction is not awaiting a signature")
    return bmoni.get_signing_payload(proposal_id=transaction["bmoni_proposal_id"])


@app.post("/v1/transactions/{transaction_id}/signature")
def submit_signature(
    transaction_id: str, payload: SignatureRequest, user: dict = Depends(current_user)
) -> dict:
    transaction = owned_transaction(transaction_id, user["id"])
    if transaction["status"] != "PENDING_SIGNATURE":
        raise HTTPException(status_code=409, detail="Transaction is not awaiting a signature")
    try:
        remote = bmoni.submit_signature(
            proposal_id=transaction["bmoni_proposal_id"], signature=payload.signature
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    local_status = "COMPLETED" if remote["status"] == "COMPLETED" else "PROCESSING"
    completed_at = now_iso() if local_status == "COMPLETED" else None
    with connection() as conn:
        conn.execute(
            "UPDATE transactions SET status = ?, bmoni_status = ?, completed_at = ? WHERE id = ?",
            (local_status, remote["status"], completed_at, transaction_id),
        )
    return {"id": transaction_id, "status": local_status, "bmoni_status": remote["status"]}


@app.post("/v1/webhooks/bmoni")
async def bmoni_webhook(
    request: Request, x_bmoni_signature: str | None = Header(default=None)
) -> dict:
    raw = await request.body()
    if settings.bmoni_webhook_secret:
        expected = hmac.new(settings.bmoni_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not x_bmoni_signature or not hmac.compare_digest(x_bmoni_signature, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    elif settings.environment != "development":
        raise HTTPException(status_code=503, detail="Webhook secret is not configured")
    try:
        event = json.loads(raw)
        event_id = str(event["id"])
        event_type = str(event["type"])
        proposal_id = str(event["proposal_id"])
        remote_status = str(event["status"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid webhook payload")
    with connection() as conn:
        if conn.execute("SELECT 1 FROM webhook_events WHERE id = ?", (event_id,)).fetchone():
            return {"received": True, "duplicate": True}
        mapping = {"COMPLETED": "COMPLETED", "FAILED": "FAILED", "PENDING": "PROCESSING"}
        local_status = mapping.get(remote_status, "PROCESSING")
        completed_at = now_iso() if local_status == "COMPLETED" else None
        conn.execute(
            "UPDATE transactions SET status = ?, bmoni_status = ?, completed_at = ? WHERE bmoni_proposal_id = ?",
            (local_status, remote_status, completed_at, proposal_id),
        )
        conn.execute(
            "INSERT INTO webhook_events VALUES (?, ?, ?, ?, 1, ?)",
            (event_id, event_type, proposal_id, json_text(event), now_iso()),
        )
    return {"received": True, "duplicate": False}


@app.post("/v1/pockets", status_code=201)
def create_pocket(payload: PocketCreateRequest, user: dict = Depends(current_user)) -> dict:
    currency = payload.currency.upper()
    if currency not in {"CNGN", "USD"}:
        raise HTTPException(status_code=422, detail="Unsupported pocket currency")
    pocket_id = new_id("pkt")
    try:
        with connection() as conn:
            conn.execute(
                "INSERT INTO pockets VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
                (pocket_id, user["id"], payload.name, payload.purpose,
                 payload.allocated_minor, currency, int(payload.protected), now_iso()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A pocket with this name already exists")
    return {"id": pocket_id, **payload.model_dump(), "currency": currency, "spent_minor": 0}


@app.get("/v1/pockets")
def list_pockets(user: dict = Depends(current_user)) -> list[dict]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM pockets WHERE user_id = ? ORDER BY created_at", (user["id"],)).fetchall()
    return [dict(row) for row in rows]


@app.post("/v1/recommendations/currency-shield", status_code=201)
def create_currency_shield(payload: CurrencyShieldRequest, user: dict = Depends(current_user)) -> dict:
    with connection() as conn:
        pocket = row_dict(conn.execute(
            "SELECT * FROM pockets WHERE id = ? AND user_id = ?", (payload.pocket_id, user["id"])
        ).fetchone())
    if not pocket:
        raise HTTPException(status_code=404, detail="Pocket not found")
    available = pocket["allocated_minor"] - pocket["spent_minor"]
    maximum = available * settings.max_fx_conversion_percent // 100
    reasons = []
    if pocket["protected"]:
        reasons.append("PROTECTED_POCKET")
    if pocket["currency"] != "CNGN" or payload.target_currency.upper() != "USD":
        reasons.append("UNSUPPORTED_PAIR")
    if payload.amount_minor > maximum:
        reasons.append("AMOUNT_EXCEEDS_SAFETY_LIMIT")
    if payload.observed_change_bps > -settings.fx_alert_threshold_bps:
        reasons.append("ALERT_THRESHOLD_NOT_REACHED")
    if reasons:
        raise HTTPException(status_code=422, detail={"status": "NOT_RECOMMENDED", "reasons": reasons})
    recommendation_id = new_id("rec")
    evidence = {
        "observed_change_bps": payload.observed_change_bps,
        "observation_window_days": payload.observation_window_days,
        "max_conversion_percent": settings.max_fx_conversion_percent,
    }
    rationale = (
        f"CNGN changed {abs(payload.observed_change_bps) / 100:.2f}% over "
        f"{payload.observation_window_days} days. Consider diversifying part of this pocket."
    )
    disclosure = "Rates can move in either direction. Conversion may include fees or spread. No money moves without approval."
    with connection() as conn:
        conn.execute(
                "INSERT INTO recommendations VALUES (?, ?, ?, 'CURRENCY_SHIELD', 'AWAITING_APPROVAL', ?, ?, ?, ?, ?, ?, NULL, ?)",
            (recommendation_id, user["id"], pocket["id"], pocket["currency"],
             payload.target_currency.upper(), payload.amount_minor, rationale, disclosure,
             json_text(evidence), now_iso()),
        )
    return {"id": recommendation_id, "status": "AWAITING_APPROVAL", "rationale": rationale,
            "risk_disclosure": disclosure, "evidence": evidence, "requires_user_approval": True}


@app.post("/v1/recommendations/{recommendation_id}/approve", status_code=201)
def approve_currency_shield(
    recommendation_id: str,
    idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
    user: dict = Depends(current_user),
) -> dict:
    with connection() as conn:
        existing = row_dict(conn.execute(
            "SELECT * FROM fx_conversions WHERE user_id = ? AND idempotency_key = ?",
            (user["id"], idempotency_key),
        ).fetchone())
        if existing:
            return existing
        recommendation = row_dict(conn.execute(
            "SELECT * FROM recommendations WHERE id = ? AND user_id = ?",
            (recommendation_id, user["id"]),
        ).fetchone())
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if recommendation["status"] != "AWAITING_APPROVAL":
        raise HTTPException(status_code=409, detail="Recommendation cannot be approved")
    quote = bmoni.get_fx_quote(amount_minor=recommendation["amount_minor"],
                               source=recommendation["source_currency"], target=recommendation["target_currency"])
    remote = bmoni.execute_fx_conversion(quote_id=quote["id"], idempotency_key=idempotency_key)
    conversion_id = new_id("fx")
    completed_at = now_iso() if remote["status"] == "COMPLETED" else None
    with connection() as conn:
        conn.execute("UPDATE recommendations SET status = 'EXECUTED' WHERE id = ?", (recommendation_id,))
        conn.execute(
            "INSERT INTO fx_conversions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (conversion_id, user["id"], recommendation_id, remote["id"], remote["status"],
             recommendation["amount_minor"], recommendation["source_currency"],
             recommendation["target_currency"], json_text(quote), idempotency_key, now_iso(), completed_at),
        )
    return {"id": conversion_id, "status": remote["status"], "quote": quote}
