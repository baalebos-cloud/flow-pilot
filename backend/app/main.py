import hashlib
import hmac
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.bmoni import BmoniError, bmoni
from app.balances import available_balance_minor, fetch_wallet_balances, minor_to_decimal
from app.config import settings
from app.database import session_scope
from app.models import ActionPlan, FxConversion, Pocket, Recommendation, Transaction, User, Wallet, WebhookEvent
from app.repositories import (
    add_audit, get_action_plan, get_fx_by_idempotency, get_pocket,
    get_recommendation, get_transaction, get_transaction_by_idempotency,
    get_transaction_by_proposal, get_user_by_email, get_user_by_id,
    get_wallet_by_user, get_webhook_event, list_user_pockets, utc_now,
)
from app.rate_limit import enforce_rate_limit
from app.schemas import (
    ActionPlanRequest, CurrencyShieldRequest, FxQuoteRequest, LoginRequest,
    PocketCreateRequest,
    ManagedWalletCreateRequest, OwnerProofChallengeRequest, RegisterRequest,
    SignatureRequest, WalletLinkRequest,
)
from app.security import create_access_token, decode_access_token, hash_password, verify_password
from app.workflow import (
    ACTION_PLAN_TRANSITIONS,
    RECOMMENDATION_TRANSITIONS,
    TRANSACTION_TRANSITIONS,
    ActionPlanStatus,
    RecommendationStatus,
    TransactionStatus,
    transition,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield  # Alembic owns schema lifecycle.


app = FastAPI(title="FlowPilot API", version="0.2.0", lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def model_dict(item) -> dict:
    return {column.name: getattr(item, column.name) for column in item.__table__.columns}


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    with session_scope() as session:
        user = get_user_by_id(session, user_id)
        if not user or user.provisioning_status != "ACTIVE":
            raise HTTPException(status_code=401, detail="User is unavailable")
        session.expunge(user)
        return user


@app.exception_handler(BmoniError)
async def bmoni_error(_: Request, exc: BmoniError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": str(exc),
            "code": exc.code,
            "retryable": exc.retryable,
        },
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "bmoni_mode": settings.bmoni_mode,
    }


@app.post("/v1/auth/register", status_code=201)
def register(payload: RegisterRequest, request: Request) -> dict:
    enforce_rate_limit(
        request,
        scope="auth-register",
        limit=settings.auth_rate_limit_per_minute,
        window_seconds=60,
    )
    email, user_id = str(payload.email).lower(), new_id("usr")
    try:
        with session_scope() as session:
            if get_user_by_email(session, email):
                raise HTTPException(status_code=409, detail="A FlowPilot account with this email already exists")
            session.add(User(id=user_id, email=email,
                             name=f"{payload.first_name} {payload.last_name}",
                             password_hash=hash_password(payload.password),
                             provisioning_status="PENDING", created_at=utc_now()))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="A FlowPilot account with this email already exists")
    try:
        remote = bmoni.create_user(
            external_id=user_id,
            email=email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone_number=payload.phone_number,
        )
    except Exception:
        with session_scope() as session:
            user = get_user_by_id(session, user_id)
            if user:
                user.provisioning_status = "FAILED"
        raise
    with session_scope() as session:
        user = get_user_by_id(session, user_id)
        if not user:
            raise HTTPException(status_code=500, detail="Provisioned user record disappeared")
        user.bmoni_user_id, user.provisioning_status = remote["id"], "ACTIVE"
        add_audit(session, event_id=new_id("aud"), actor_user_id=user_id,
                  action="BMONI_USER_PROVISION", resource_type="USER",
                  resource_id=user_id, outcome="SUCCEEDED")
        session.flush()
        result = model_dict(user)
        result.pop("password_hash")
    return {"access_token": create_access_token(user_id), "token_type": "bearer", "user": result}


@app.post("/v1/auth/login")
def login(payload: LoginRequest, request: Request) -> dict:
    enforce_rate_limit(
        request,
        scope="auth-login",
        limit=settings.auth_rate_limit_per_minute,
        window_seconds=60,
    )
    with session_scope() as session:
        user = get_user_by_email(session, str(payload.email).lower())
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if user.provisioning_status != "ACTIVE":
            raise HTTPException(status_code=403, detail="Account provisioning is incomplete")
        user_id = user.id
    return {"access_token": create_access_token(user_id), "token_type": "bearer"}


@app.get("/v1/me")
def me(user: User = Depends(current_user)) -> dict:
    result = model_dict(user)
    result.pop("password_hash")
    return result


@app.post("/v1/wallets/link", status_code=201)
def link_wallet(payload: WalletLinkRequest, user: User = Depends(current_user)) -> dict:
    currency = payload.currency.upper()
    if currency != "CNGN":
        raise HTTPException(status_code=422, detail="The MVP currently supports CNGN only")
    with session_scope() as session:
        if get_wallet_by_user(session, user.id):
            raise HTTPException(status_code=409, detail="This user already has a linked wallet")
    remote = bmoni.link_wallet(bmoni_user_id=user.bmoni_user_id or "",
                               address=payload.wallet_address, currency=currency)
    wallet_id = new_id("wal")
    try:
        with session_scope() as session:
            session.add(Wallet(id=wallet_id, user_id=user.id, bmoni_wallet_id=remote["id"],
                               wallet_address=payload.wallet_address, currency=currency,
                               status=remote["status"], created_at=utc_now()))
            add_audit(session, event_id=new_id("aud"), actor_user_id=user.id,
                      action="WALLET_LINK", resource_type="WALLET",
                      resource_id=wallet_id, outcome="SUCCEEDED")
    except IntegrityError:
        raise HTTPException(status_code=409, detail="This user or wallet address is already linked")
    return {"id": wallet_id, "bmoni_wallet_id": remote["id"],
            "status": remote["status"], "currency": currency}


@app.post("/v1/wallets/owner-proof-challenges", status_code=201)
def create_owner_proof_challenge(
    payload: OwnerProofChallengeRequest, user: User = Depends(current_user)
) -> dict:
    currency = payload.currency.upper()

    if currency != "CNGN":
        raise HTTPException(status_code=422, detail="The MVP currently supports CNGN only")
    if not user.bmoni_user_id:
        raise HTTPException(status_code=409, detail="BMONI user provisioning is incomplete")
    challenge = bmoni.create_owner_proof_challenge(
        bmoni_user_id=user.bmoni_user_id,
        owner_address=payload.owner_address,
        currency=currency,
    )
    required = {"challengeId", "groupId", "message", "expiresAt"}
    if not isinstance(challenge, dict) or not required.issubset(challenge):
        raise BmoniError(
            "BMONI owner-proof response is invalid", code="BMONI_INVALID_RESPONSE"
        )
    return {key: challenge[key] for key in required}


@app.post("/v1/wallets/managed", status_code=201)
def create_managed_wallet(
    payload: ManagedWalletCreateRequest, user: User = Depends(current_user)
) -> dict:
    currency = payload.currency.upper()
    if currency != "CNGN":
        raise HTTPException(status_code=422, detail="The MVP currently supports CNGN only")
    if not user.bmoni_user_id:
        raise HTTPException(status_code=409, detail="BMONI user provisioning is incomplete")
    with session_scope() as session:
        existing = get_wallet_by_user(session, user.id)
        if existing:
            return model_dict(existing)
    remote = bmoni.create_managed_wallet(
        bmoni_user_id=user.bmoni_user_id,
        owner_address=payload.owner_address,
        currency=currency,
        challenge_id=payload.challenge_id,
        signature=payload.signature,
    )
    try:
        remote_id = str(remote["id"])
        wallet_address = str(remote["walletAddress"])
        active = bool(remote["isActive"])
    except (KeyError, TypeError) as exc:
        raise BmoniError(
            "BMONI managed-wallet response is invalid", code="BMONI_INVALID_RESPONSE"
        ) from exc
    if not wallet_address.startswith("0x"):
        raise BmoniError(
            "BMONI managed wallet has no deployed address",
            code="BMONI_WALLET_NOT_DEPLOYED",
            retryable=True,
        )
    wallet_id = new_id("wal")
    status = "ACTIVE" if active else "PENDING"
    try:
        with session_scope() as session:
            session.add(
                Wallet(
                    id=wallet_id,
                    user_id=user.id,
                    bmoni_wallet_id=remote_id,
                    wallet_address=wallet_address,
                    currency=currency,
                    status=status,
                    created_at=utc_now(),
                )
            )
            add_audit(
                session,
                event_id=new_id("aud"),
                actor_user_id=user.id,
                action="MANAGED_WALLET_CREATE",
                resource_type="WALLET",
                resource_id=wallet_id,
                outcome="SUCCEEDED",
            )
    except IntegrityError:
        with session_scope() as session:
            existing = get_wallet_by_user(session, user.id)
            if existing:
                return model_dict(existing)
        raise
    return {
        "id": wallet_id,
        "bmoni_wallet_id": remote_id,
        "wallet_address": wallet_address,
        "currency": currency,
        "status": status,
    }


@app.get("/v1/wallets/balances")
def wallet_balances(user: User = Depends(current_user)) -> dict:
    if not user.bmoni_user_id:
        raise HTTPException(status_code=409, detail="BMONI user provisioning is incomplete")
    balances = fetch_wallet_balances(bmoni, bmoni_user_id=user.bmoni_user_id)
    return {"balances": [balance.model_dump() for balance in balances]}


@app.post("/v1/fx/quotes")
def create_fx_quote(
    payload: FxQuoteRequest, user: User = Depends(current_user)
) -> dict:
    if not user.bmoni_user_id:
        raise HTTPException(status_code=409, detail="BMONI user provisioning is incomplete")
    source = payload.source_currency.upper()
    target = payload.target_currency.upper()
    if (source, target) != ("CNGN", "USD"):
        raise HTTPException(status_code=422, detail="The MVP supports CNGN to USD only")
    balance_minor = available_balance_minor(
        bmoni, bmoni_user_id=user.bmoni_user_id, currency=source
    )
    if payload.amount_minor > balance_minor:
        raise HTTPException(status_code=422, detail="Insufficient authoritative balance")
    quote = bmoni.get_fx_quote(
        bmoni_user_id=user.bmoni_user_id,
        amount_decimal=minor_to_decimal(payload.amount_minor, "NGN"),
        source="NGN",
        target=target,
    )
    required = {
        "quoteId",
        "fromCurrency",
        "toCurrency",
        "amountIn",
        "amountOut",
        "exchangeRate",
        "fees",
        "quotedAt",
        "expiresAt",
        "expiresInSeconds",
    }
    if not isinstance(quote, dict) or not required.issubset(quote):
        raise BmoniError("BMONI quote response is invalid", code="BMONI_INVALID_RESPONSE")
    return {
        "quote_id": quote["quoteId"],
        "source_currency": source,
        "target_currency": target,
        "source_amount_minor": payload.amount_minor,
        "target_amount": quote["amountOut"],
        "exchange_rate": quote["exchangeRate"],
        "fees": quote["fees"],
        "quoted_at": quote["quotedAt"],
        "expires_at": quote["expiresAt"],
        "expires_in_seconds": quote["expiresInSeconds"],
        "money_has_moved": False,
        "requires_user_approval": True,
    }


@app.post("/v1/action-plans", status_code=201)
def create_action_plan(payload: ActionPlanRequest, user: User = Depends(current_user)) -> dict:
    currency, failures = payload.currency.upper(), []
    if currency != "CNGN":
        failures.append("UNSUPPORTED_CURRENCY")

    if payload.amount_minor > payload.available_balance_minor:
        failures.append("INSUFFICIENT_BALANCE")

    if payload.amount_minor > settings.max_transaction_minor:
        failures.append("PER_TRANSACTION_LIMIT_EXCEEDED")

    if failures:
        raise HTTPException(status_code=422, detail={"risk_status": "REJECTED", "reasons": failures})
    plan_id, expected = new_id("plan"), payload.available_balance_minor - payload.amount_minor
    with session_scope() as session:
        session.add(ActionPlan(id=plan_id, user_id=user.id, action_type="BANK_WITHDRAWAL",
                               amount_minor=payload.amount_minor, currency=currency,
                               recipient_name=payload.recipient_name, reason=payload.message,
                               available_balance_minor=payload.available_balance_minor,
                               expected_balance_minor=expected, risk_status="PASSED",
                               approval_status="AWAITING_USER_APPROVAL", created_at=utc_now()))
    return {"id": plan_id, "action_type": "BANK_WITHDRAWAL", "amount_minor": payload.amount_minor,
            "currency": currency, "recipient_name": payload.recipient_name,
            "available_balance_minor": payload.available_balance_minor,
            "expected_balance_minor": expected, "risk_status": "PASSED",
            "approval_status": "AWAITING_USER_APPROVAL", "requires_user_approval": True,
            "money_has_moved": False}


@app.post("/v1/action-plans/{plan_id}/approve", status_code=201)
def approve_action_plan(plan_id: str,
                        request: Request,
                        idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
                        user: User = Depends(current_user)) -> dict:
    enforce_rate_limit(
        request,
        scope=f"financial-approval:{user.id}",
        limit=settings.financial_rate_limit_per_minute,
        window_seconds=60,
    )
    with session_scope() as session:
        existing = get_transaction_by_idempotency(session, user.id, idempotency_key)
        if existing:
            return model_dict(existing)
        plan = session.scalar(select(ActionPlan).where(ActionPlan.id == plan_id,
                              ActionPlan.user_id == user.id).with_for_update())
        if not plan:
            raise HTTPException(status_code=404, detail="Action plan not found")
        if plan.approval_status != ActionPlanStatus.AWAITING_USER_APPROVAL:
            raise HTTPException(status_code=409, detail="Action plan cannot be approved in its current state")
        plan.approval_status = transition(
            plan.approval_status,
            ActionPlanStatus.CREATING_PROPOSAL,
            ACTION_PLAN_TRANSITIONS,
        )
        snapshot = (plan.amount_minor, plan.currency, plan.recipient_name)
    try:
        proposal = bmoni.create_withdrawal_proposal(
            bmoni_user_id=user.bmoni_user_id or "",
            amount_minor=snapshot[0],
            currency=snapshot[1],
            recipient_name=snapshot[2],
        )
    except Exception:
        with session_scope() as session:
            failed_plan = get_action_plan(session, plan_id, user.id)
            if failed_plan and failed_plan.approval_status == ActionPlanStatus.CREATING_PROPOSAL:
                failed_plan.approval_status = transition(
                    failed_plan.approval_status,
                    ActionPlanStatus.FAILED,
                    ACTION_PLAN_TRANSITIONS,
                )
                add_audit(
                    session,
                    event_id=new_id("aud"),
                    actor_user_id=user.id,
                    action="WITHDRAWAL_APPROVE",
                    resource_type="ACTION_PLAN",
                    resource_id=plan_id,
                    outcome="FAILED",
                )
        raise
    transaction_id = new_id("txn")
    with session_scope() as session:
        plan = get_action_plan(session, plan_id, user.id)
        if not plan:
            raise HTTPException(status_code=404, detail="Action plan not found")
        plan.approval_status = transition(
            plan.approval_status, ActionPlanStatus.APPROVED, ACTION_PLAN_TRANSITIONS
        )
        session.add(Transaction(id=transaction_id, user_id=user.id, action_plan_id=plan_id,
                                bmoni_proposal_id=proposal["id"], amount_minor=plan.amount_minor,
                                currency=plan.currency, status="PENDING_SIGNATURE",
                                bmoni_status=proposal["status"], idempotency_key=idempotency_key,
                                created_at=utc_now()))
        add_audit(session, event_id=new_id("aud"), actor_user_id=user.id,
                  action="WITHDRAWAL_APPROVE", resource_type="TRANSACTION",
                  resource_id=transaction_id, outcome="SUCCEEDED")
    return {"id": transaction_id, "bmoni_proposal_id": proposal["id"], "status": "PENDING_SIGNATURE"}


def owned_transaction(transaction_id: str, user_id: str) -> Transaction:
    with session_scope() as session:
        item = get_transaction(session, transaction_id, user_id)
        if not item:
            raise HTTPException(status_code=404, detail="Transaction not found")
        session.expunge(item)
        return item


@app.get("/v1/transactions/{transaction_id}")
def read_transaction(transaction_id: str, user: User = Depends(current_user)) -> dict:
    return model_dict(owned_transaction(transaction_id, user.id))

@app.get(
    "/v1/transactions/{transaction_id}/signing-payload"
)
def signing_payload(
    transaction_id: str,
    user: dict = Depends(current_user),
) -> dict:
    transaction = owned_transaction(
        transaction_id,
        user["id"],
    )

@app.get("/v1/transactions/{transaction_id}/signing-payload")
def signing_payload(transaction_id: str, user: User = Depends(current_user)) -> dict:
    item = owned_transaction(transaction_id, user.id)
    if item.status != "PENDING_SIGNATURE":
        raise HTTPException(status_code=409, detail="Transaction is not awaiting a signature")
    return bmoni.get_signing_payload(proposal_id=item.bmoni_proposal_id)

    return bmoni.get_signing_payload(
        proposal_id=transaction["bmoni_proposal_id"]
    )

@app.post("/v1/transactions/{transaction_id}/signature")
def submit_signature(transaction_id: str, payload: SignatureRequest,
                     request: Request,
                     user: User = Depends(current_user)) -> dict:
    enforce_rate_limit(
        request,
        scope=f"financial-signature:{user.id}",
        limit=settings.financial_rate_limit_per_minute,
        window_seconds=60,
    )
    item = owned_transaction(transaction_id, user.id)
    if item.status != "PENDING_SIGNATURE":
        raise HTTPException(status_code=409, detail="Transaction is not awaiting a signature")
    try:
        remote = bmoni.submit_signature(proposal_id=item.bmoni_proposal_id, signature=payload.signature)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    local_status = "COMPLETED" if remote["status"] == "COMPLETED" else "PROCESSING"
    with session_scope() as session:
        stored = get_transaction(session, transaction_id, user.id)
        if not stored:
            raise HTTPException(status_code=404, detail="Transaction not found")
        stored.status = transition(
            stored.status, TransactionStatus(local_status), TRANSACTION_TRANSITIONS
        )
        stored.bmoni_status = remote["status"]
        stored.completed_at = utc_now() if local_status == "COMPLETED" else None
        add_audit(session, event_id=new_id("aud"), actor_user_id=user.id,
                  action="SIGNATURE_SUBMIT", resource_type="TRANSACTION",
                  resource_id=transaction_id, outcome="SUCCEEDED")
    return {"id": transaction_id, "status": local_status, "bmoni_status": remote["status"]}


@app.post("/v1/webhooks/bmoni")
async def bmoni_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(default=None),
    x_webhook_id: str | None = Header(default=None),
    x_source_event_id: str | None = Header(default=None),
) -> dict:
    raw = await request.body()

    if settings.bmoni_webhook_secret:
        expected = hmac.new(
            settings.bmoni_webhook_secret.encode(), raw, hashlib.sha256
        ).hexdigest()
        if not x_webhook_signature or not hmac.compare_digest(
            x_webhook_signature, expected
        ):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    elif settings.environment != "development":
        raise HTTPException(
            status_code=503,
            detail="Webhook secret is not configured",
        )

    try:
        event = json.loads(raw)
        event_id, event_type = str(event["id"]), str(event["eventType"])
        payload = event["payload"]
        if not isinstance(payload, dict):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid webhook payload")
    if not x_webhook_id or not hmac.compare_digest(x_webhook_id, event_id):
        raise HTTPException(status_code=422, detail="Webhook ID header does not match body")

    proposal_id = str(
        payload.get("proposalId")
        or payload.get("proposal_id")
        or payload.get("withdrawalId")
        or ""
    )
    event_status = event_type.rsplit(".", maxsplit=1)[-1].upper()
    remote_status = str(payload.get("status") or event_status).upper()
    with session_scope() as session:
        if get_webhook_event(session, event_id):
            return {"received": True, "duplicate": True}
        item = get_transaction_by_proposal(session, proposal_id) if proposal_id else None
        local_status = {"COMPLETED": "COMPLETED", "FAILED": "FAILED",
                        "PENDING": "PROCESSING"}.get(remote_status, "REQUIRES_REVIEW")
        if item and item.status not in {"COMPLETED", "FAILED"}:
            item.status = transition(
                item.status, TransactionStatus(local_status), TRANSACTION_TRANSITIONS
            )
            item.bmoni_status = remote_status
            item.completed_at = utc_now() if local_status == "COMPLETED" else None
        external_id = x_source_event_id or proposal_id or event_id
        session.add(WebhookEvent(id=event_id, event_type=event_type, external_id=external_id,
                                 payload_json=json.dumps(event, separators=(",", ":"), sort_keys=True),
                                 processed=True, created_at=utc_now()))
    return {"received": True, "duplicate": False}


@app.post("/v1/pockets", status_code=201)
def create_pocket(payload: PocketCreateRequest, user: User = Depends(current_user)) -> dict:
    currency = payload.currency.upper()

    if currency not in {"CNGN", "USD"}:
        raise HTTPException(
            status_code=422,
            detail="Unsupported pocket currency",
        )

    pocket_id = new_id("pkt")

    try:
        with session_scope() as session:
            session.add(Pocket(id=pocket_id, user_id=user.id, name=payload.name,
                               purpose=payload.purpose, allocated_minor=payload.allocated_minor,
                               spent_minor=0, currency=currency, protected=payload.protected,
                               created_at=utc_now()))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="A pocket with this name already exists")
    return {"id": pocket_id, **payload.model_dump(), "currency": currency, "spent_minor": 0}


@app.get("/v1/pockets")
def list_pockets(user: User = Depends(current_user)) -> list[dict]:
    with session_scope() as session:
        return [model_dict(item) for item in list_user_pockets(session, user.id)]


@app.post("/v1/recommendations/currency-shield", status_code=201)
def create_currency_shield(payload: CurrencyShieldRequest,
                           user: User = Depends(current_user)) -> dict:
    with session_scope() as session:
        pocket = get_pocket(session, payload.pocket_id, user.id)
        if not pocket:
            raise HTTPException(status_code=404, detail="Pocket not found")
        available, reasons = pocket.allocated_minor - pocket.spent_minor, []
        maximum = available * settings.max_fx_conversion_percent // 100
        if pocket.protected:
            reasons.append("PROTECTED_POCKET")
        if pocket.currency != "CNGN" or payload.target_currency.upper() != "USD":
            reasons.append("UNSUPPORTED_PAIR")
        if payload.amount_minor > maximum:
            reasons.append("AMOUNT_EXCEEDS_SAFETY_LIMIT")
        if payload.observed_change_bps > -settings.fx_alert_threshold_bps:
            reasons.append("ALERT_THRESHOLD_NOT_REACHED")
        if reasons:
            raise HTTPException(status_code=422, detail={"status": "NOT_RECOMMENDED", "reasons": reasons})
        recommendation_id = new_id("rec")
        evidence = {"observed_change_bps": payload.observed_change_bps,
                    "observation_window_days": payload.observation_window_days,
                    "max_conversion_percent": settings.max_fx_conversion_percent}
        rationale = (f"CNGN changed {abs(payload.observed_change_bps) / 100:.2f}% over "
                     f"{payload.observation_window_days} days. Consider diversifying part of this pocket.")
        disclosure = "Rates can move in either direction. Conversion may include fees or spread. No money moves without approval."
        session.add(Recommendation(id=recommendation_id, user_id=user.id, pocket_id=pocket.id,
                                   type="CURRENCY_SHIELD", status="AWAITING_APPROVAL",
                                   source_currency=pocket.currency, target_currency=payload.target_currency.upper(),
                                   amount_minor=payload.amount_minor, rationale=rationale,
                                   risk_disclosure=disclosure, evidence_json=json.dumps(evidence),
                                   created_at=utc_now()))
    return {"id": recommendation_id, "status": "AWAITING_APPROVAL", "rationale": rationale,
            "risk_disclosure": disclosure, "evidence": evidence, "requires_user_approval": True}

    return {
        "id": recommendation_id,
        "status": "AWAITING_APPROVAL",
        "rationale": rationale,
        "risk_disclosure": disclosure,
        "evidence": evidence,
        "requires_user_approval": True,
    }

@app.post("/v1/recommendations/{recommendation_id}/approve", status_code=201)
def approve_currency_shield(recommendation_id: str,
                            request: Request,
                            idempotency_key: str = Header(min_length=8, max_length=128, alias="Idempotency-Key"),
                            user: User = Depends(current_user)) -> dict:
    enforce_rate_limit(
        request,
        scope=f"financial-fx:{user.id}",
        limit=settings.financial_rate_limit_per_minute,
        window_seconds=60,
    )
    with session_scope() as session:
        existing = get_fx_by_idempotency(session, user.id, idempotency_key)
        if existing:
            return model_dict(existing)
        recommendation = session.scalar(select(Recommendation).where(
            Recommendation.id == recommendation_id, Recommendation.user_id == user.id).with_for_update())
        if not recommendation:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        if recommendation.status != RecommendationStatus.AWAITING_APPROVAL:
            raise HTTPException(status_code=409, detail="Recommendation cannot be approved")
        recommendation.status = transition(
            recommendation.status,
            RecommendationStatus.EXECUTING,
            RECOMMENDATION_TRANSITIONS,
        )
        snapshot = (recommendation.amount_minor, recommendation.source_currency,
                    recommendation.target_currency)
    if snapshot[0] is None or snapshot[1] is None or snapshot[2] is None:
        raise HTTPException(status_code=409, detail="Recommendation is incomplete")
    try:
        quote = bmoni.get_fx_quote(
            bmoni_user_id=user.bmoni_user_id or "",
            amount_decimal=minor_to_decimal(snapshot[0], "NGN"),
            source="NGN",
            target=snapshot[2],
        )
        remote = bmoni.execute_fx_conversion(
            quote_id=quote["quoteId"], idempotency_key=idempotency_key
        )
    except Exception:
        with session_scope() as session:
            failed_recommendation = get_recommendation(
                session, recommendation_id, user.id
            )
            if (
                failed_recommendation
                and failed_recommendation.status == RecommendationStatus.EXECUTING
            ):
                failed_recommendation.status = transition(
                    failed_recommendation.status,
                    RecommendationStatus.FAILED,
                    RECOMMENDATION_TRANSITIONS,
                )
                add_audit(
                    session,
                    event_id=new_id("aud"),
                    actor_user_id=user.id,
                    action="FX_CONVERSION_APPROVE",
                    resource_type="RECOMMENDATION",
                    resource_id=recommendation_id,
                    outcome="FAILED",
                )
        raise
    conversion_id = new_id("fx")
    with session_scope() as session:
        recommendation = get_recommendation(session, recommendation_id, user.id)
        if not recommendation:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        recommendation.status = transition(
            recommendation.status,
            RecommendationStatus.EXECUTED,
            RECOMMENDATION_TRANSITIONS,
        )
        session.add(FxConversion(id=conversion_id, user_id=user.id,
                                 recommendation_id=recommendation_id,
                                 bmoni_conversion_id=remote["id"], status=remote["status"],
                                 source_amount_minor=snapshot[0], source_currency=snapshot[1],
                                 target_currency=snapshot[2], quote_json=json.dumps(quote),
                                 idempotency_key=idempotency_key, created_at=utc_now(),
                                 completed_at=utc_now() if remote["status"] == "COMPLETED" else None))
        add_audit(session, event_id=new_id("aud"), actor_user_id=user.id,
                  action="FX_CONVERSION_APPROVE", resource_type="FX_CONVERSION",
                  resource_id=conversion_id, outcome="SUCCEEDED")
    return {"id": conversion_id, "status": remote["status"], "quote": quote}
