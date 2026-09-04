import hashlib
import hmac
import json
import uuid

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse
from jwt import InvalidTokenError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.ai.router import build_ai_router
from app.bmoni import BmoniError, bmoni
from app.balances import (
    available_balance_minor,
    fetch_wallet_balances,
    minor_to_decimal,
)
from app.config import settings
from app.database import session_scope
from app.models import (
    ActionPlan,
    FxConversion,
    Pocket,
    Recommendation,
    Transaction,
    User,
    Wallet,
    WebhookEvent,
)
from app.repositories import (
    add_audit,
    get_action_plan,
    get_fx_by_idempotency,
    get_fx_conversion,
    get_pocket as get_pocket_record,
    get_recommendation,
    get_transaction,
    get_transaction_by_idempotency,
    get_transaction_by_proposal,
    get_user_by_email,
    get_user_by_id,
    get_wallet_by_user,
    get_webhook_event,
    list_user_pockets,
    utc_now,
)
from app.rate_limit import enforce_rate_limit
from app.schemas import (
    ActionPlanRequest,
    CurrencyShieldRequest,
    FxQuoteRequest,
    InvestmentOpportunityResponse,
    LoginRequest,
    ManagedWalletCreateRequest,
    OwnerProofChallengeRequest,
    PocketCreateRequest,
    PocketTransferRequest,
    ProposalSignatureRequest,
    RegisterRequest,
    SignatureRequest,
    TransactionCategorizeRequest,
    WalletLinkRequest,
)
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.workflow import (
    ACTION_PLAN_TRANSITIONS,
    RECOMMENDATION_TRANSITIONS,
    ActionPlanStatus,
    RecommendationStatus,
    TransactionStatus,
    transition,
)


SUPPORTED_POCKET_CURRENCIES = {"CNGN", "USD"}


def new_id(prefix: str) -> str:
    """Create a unique application identifier."""
    return f"{prefix}_{uuid.uuid4().hex}"


def model_dict(item) -> dict:
    """Convert a SQLAlchemy model into a JSON-safe dictionary."""
    return {
        column.name: getattr(item, column.name)
        for column in item.__table__.columns
    }


def _pocket_summary(pocket: Pocket) -> dict:
    """Return the public summary of a pocket."""
    return {
        "id": pocket.id,
        "name": pocket.name,
        "purpose": pocket.purpose,
        "allocated_minor": pocket.allocated_minor,
        "spent_minor": pocket.spent_minor,
        "available_minor": pocket.allocated_minor - pocket.spent_minor,
        "currency": pocket.currency,
        "protected": pocket.protected,
        "created_at": pocket.created_at,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Keep schema lifecycle under Alembic rather than creating tables here."""
    yield


app = FastAPI(
    title="FlowPilot API",
    version="0.2.0",
    lifespan=lifespan,
)


security = HTTPBearer()


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Resolve the authenticated active FlowPilot user."""
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
        )

    with session_scope() as session:
        user = get_user_by_id(session, user_id)

        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not found",
            )

        if user.provisioning_status != "ACTIVE":
            raise HTTPException(
                status_code=409,
                detail="BMONI user provisioning is not active",
            )

        session.expunge(user)
        return user


app.include_router(build_ai_router(current_user))


@app.exception_handler(BmoniError)
async def handle_bmoni_error(request: Request, exc: BmoniError):
    """Normalize BMONI failures into the API error format."""
    status_code = 503 if exc.retryable else exc.status_code

    return JSONResponse(
        status_code=status_code,
        content={"detail": str(exc), "code": exc.code, "retryable": exc.retryable},
    )


@app.get("/health", status_code=200)
def health_check() -> dict:
    """Health check endpoint for platform monitoring."""
    return {"status":"ok","bmoni_mode":"mock"}
    
@app.post("/v1/auth/register", status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
) -> dict:
    """Register a FlowPilot user and provision the corresponding BMONI user."""
    enforce_rate_limit(
        request,
        scope="auth-register",
        limit=settings.auth_rate_limit_per_minute,
        window_seconds=60,
    )

    email = str(payload.email).lower()
    user_id = new_id("usr")

    try:
        with session_scope() as session:
            if get_user_by_email(session, email):
                raise HTTPException(
                    status_code=409,
                    detail="A FlowPilot account with this email already exists",
                )

            session.add(
                User(
                    id=user_id,
                    email=email,
                    name=f"{payload.first_name} {payload.last_name}",
                    password_hash=hash_password(payload.password),
                    provisioning_status="PENDING",
                    created_at=utc_now(),
                )
            )
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A FlowPilot account with this email already exists",
        )

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
            raise HTTPException(
                status_code=500,
                detail="Provisioned user record disappeared",
            )

        user.bmoni_user_id = remote["id"]
        user.provisioning_status = "ACTIVE"

        add_audit(
            session,
            event_id=new_id("aud"),
            actor_user_id=user.id,
            action="AUTH_REGISTER",
            resource_type="USER",
            resource_id=user.id,
            outcome="SUCCESS",
        )

        session.flush()

        result = model_dict(user)
        result.pop("password_hash", None)

    return {
        "access_token": create_access_token(user_id),
        "token_type": "bearer",
        "user": result,
    }


@app.post("/v1/auth/login")
def login(
    payload: LoginRequest,
    request: Request,
) -> dict:
    """Authenticate an active FlowPilot user."""
    enforce_rate_limit(
        request,
        scope="auth-login",
        limit=settings.auth_rate_limit_per_minute,
        window_seconds=60,
    )

    email = str(payload.email).lower()

    with session_scope() as session:
        user = get_user_by_email(session, email)

        if not user or not verify_password(
            payload.password,
            user.password_hash,
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password",
            )

        if user.provisioning_status != "ACTIVE":
            raise HTTPException(
                status_code=409,
                detail="BMONI user provisioning is not active",
            )

        result = model_dict(user)
        result.pop("password_hash", None)

    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": result,
    }


@app.get("/v1/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    """Return the authenticated user's profile."""
    result = model_dict(user)
    result.pop("password_hash", None)
    return result


@app.post("/v1/wallets/link", status_code=201)
def link_wallet(
    payload: WalletLinkRequest,
    user: User = Depends(current_user),
) -> dict:
    """Link a user's external wallet."""
    currency = payload.currency.upper()

    remote = bmoni.link_wallet(
        bmoni_user_id=user.bmoni_user_id or "",
        address=payload.wallet_address,
        currency=currency,
    )

    with session_scope() as session:
        existing = get_wallet_by_user(session, user.id)

        if existing:
            raise HTTPException(
                status_code=409,
                detail="A wallet is already linked to this account",
            )

        wallet = Wallet(
            id=new_id("wal"),
            user_id=user.id,
            bmoni_wallet_id=remote["id"],
            wallet_address=payload.wallet_address,
            currency=currency,
            status=remote["status"],
            created_at=utc_now(),
        )

        session.add(wallet)
        session.flush()

        return model_dict(wallet)


@app.post("/v1/wallets/owner-proof/challenge")
def create_owner_proof_challenge(
    payload: OwnerProofChallengeRequest,
    user: User = Depends(current_user),
) -> dict:
    """Create a BMONI owner-proof challenge."""
    if not user.bmoni_user_id:
        raise HTTPException(
            status_code=409,
            detail="BMONI user provisioning is incomplete",
        )

    return bmoni.create_owner_proof_challenge(
        bmoni_user_id=user.bmoni_user_id,
        owner_address=payload.owner_address,
        currency=payload.currency.upper(),
    )


@app.post("/v1/wallets/managed", status_code=201)
def create_managed_wallet(
    payload: ManagedWalletCreateRequest,
    user: User = Depends(current_user),
) -> dict:
    """Create a managed BMONI wallet after owner verification."""
    if not user.bmoni_user_id:
        raise HTTPException(
            status_code=409,
            detail="BMONI user provisioning is incomplete",
        )

    remote = bmoni.create_managed_wallet(
        bmoni_user_id=user.bmoni_user_id,
        owner_address=payload.owner_address,
        currency=payload.currency.upper(),
        challenge_id=payload.challenge_id,
        signature=payload.signature,
    )

    with session_scope() as session:
        wallet = get_wallet_by_user(session, user.id)

        if wallet is None:
            wallet = Wallet(
                id=new_id("wal"),
                user_id=user.id,
                wallet_address=payload.owner_address,
                currency=payload.currency.upper(),
                status="ACTIVE",
                created_at=utc_now(),
            )
            session.add(wallet)

        wallet.bmoni_wallet_id = remote["id"]
        wallet.status = "ACTIVE"

        session.flush()

        return model_dict(wallet)


@app.get("/v1/wallets")
def list_wallets(user: User = Depends(current_user)) -> dict:
    """List wallets belonging to the authenticated BMONI user."""
    if not user.bmoni_user_id:
        raise HTTPException(
            status_code=409,
            detail="BMONI user provisioning is incomplete",
        )

    return bmoni.list_wallets(
        bmoni_user_id=user.bmoni_user_id,
    )


@app.get("/v1/wallets/balances")
def wallet_balances(user: User = Depends(current_user)) -> dict:
    """Return authoritative wallet balances from BMONI."""
    if not user.bmoni_user_id:
        raise HTTPException(
            status_code=409,
            detail="BMONI user provisioning is incomplete",
        )

    balances = fetch_wallet_balances(
        bmoni,
        bmoni_user_id=user.bmoni_user_id,
    )

    return {
        "balances": [
            balance.model_dump()
            for balance in balances
        ]
    }


@app.post("/v1/fx/quotes")
def create_fx_quote(
    payload: FxQuoteRequest,
    user: User = Depends(current_user),
) -> dict:
    """Create an FX quote after checking authoritative balance."""
    if not user.bmoni_user_id:
        raise HTTPException(
            status_code=409,
            detail="BMONI user provisioning is incomplete",
        )

    source = payload.source_currency.upper()
    target = payload.target_currency.upper()

    if (source, target) != ("CNGN", "USD"):
        raise HTTPException(
            status_code=422,
            detail="The MVP supports CNGN to USD only",
        )

    balance_minor = available_balance_minor(
        bmoni,
        bmoni_user_id=user.bmoni_user_id,
        currency=source,
    )

    if payload.amount_minor > balance_minor:
        raise HTTPException(
            status_code=422,
            detail="Insufficient authoritative balance",
        )

    quote = bmoni.get_fx_quote(
        bmoni_user_id=user.bmoni_user_id,
        amount_decimal=minor_to_decimal(
            payload.amount_minor,
            "NGN",
        ),
        source="NGN",
        target=target,
    )

    return quote


@app.post("/v1/action-plans", status_code=201)
def create_action_plan(
    payload: ActionPlanRequest,
    user: User = Depends(current_user),
) -> dict:
    """Create an action plan after applying transaction safety rules."""
    currency = payload.currency.upper()
    failures = []

    if currency != "CNGN":
        failures.append("UNSUPPORTED_CURRENCY")

    if payload.amount_minor > payload.available_balance_minor:
        failures.append("INSUFFICIENT_BALANCE")

    if payload.amount_minor > settings.max_transaction_minor:
        failures.append("PER_TRANSACTION_LIMIT_EXCEEDED")

    if failures:
        raise HTTPException(
            status_code=422,
            detail={
                "risk_status": "REJECTED",
                "reasons": failures,
            },
        )

    plan_id = new_id("plan")
    expected = (
        payload.available_balance_minor
        - payload.amount_minor
    )

    with session_scope() as session:
        session.add(
            ActionPlan(
                id=plan_id,
                user_id=user.id,
                action_type="PAYMENT",
                amount_minor=payload.amount_minor,
                currency=currency,
                recipient_name=payload.recipient_name,
                reason=payload.message,
                available_balance_minor=payload.available_balance_minor,
                expected_balance_minor=expected,
                risk_status="APPROVED",
                approval_status="AWAITING_USER_APPROVAL",
                created_at=utc_now(),
            )
        )

    return {
        "id": plan_id,
        "risk_status": "APPROVED",
        "approval_status": "AWAITING_USER_APPROVAL",
        "expected_balance_minor": expected,
    }


@app.post("/v1/action-plans/{plan_id}/approve", status_code=201)
def approve_action_plan(
    plan_id: str,
    request: Request,
    idempotency_key: str = Header(
        min_length=8,
        max_length=128,
        alias="Idempotency-Key",
    ),
    user: User = Depends(current_user),
) -> dict:
    """Approve an action plan and create a BMONI withdrawal proposal."""
    enforce_rate_limit(
        request,
        scope=f"financial-approval:{user.id}",
        limit=settings.financial_rate_limit_per_minute,
        window_seconds=60,
    )

    with session_scope() as session:
        existing = get_transaction_by_idempotency(
            session,
            user.id,
            idempotency_key,
        )

        if existing:
            return model_dict(existing)

        plan = session.scalar(
            select(ActionPlan)
            .where(
                ActionPlan.id == plan_id,
                ActionPlan.user_id == user.id,
            )
            .with_for_update()
        )

        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Action plan not found",
            )

        if plan.approval_status != ActionPlanStatus.AWAITING_USER_APPROVAL:
            raise HTTPException(
                status_code=409,
                detail="Action plan cannot be approved",
            )

        plan.approval_status = transition(
            plan.approval_status,
            ActionPlanStatus.CREATING_PROPOSAL,
            ACTION_PLAN_TRANSITIONS,
        )

        wallet = get_wallet_by_user(session, user.id)

        if not wallet or not wallet.bmoni_wallet_id:
            raise HTTPException(
                status_code=409,
                detail="A managed BMONI wallet is required",
            )

        snapshot = (
            plan.amount_minor,
            plan.currency,
            plan.recipient_name,
            user.bmoni_user_id,
            wallet.bmoni_wallet_id,
        )

    try:
        if not snapshot[3]:
            raise HTTPException(
                status_code=409,
                detail="BMONI user provisioning is incomplete",
            )

        remote = bmoni.create_withdrawal_proposal(
            bmoni_user_id=snapshot[3],
            amount_minor=snapshot[0],
            currency=snapshot[1],
            recipient_name=snapshot[2],
        )

        proposal_id = remote["id"]

    except Exception:
        with session_scope() as session:
            failed_plan = get_action_plan(
                session,
                plan_id,
                user.id,
            )

            if (
                failed_plan
                and failed_plan.approval_status
                == ActionPlanStatus.CREATING_PROPOSAL
            ):
                failed_plan.approval_status = transition(
                    failed_plan.approval_status,
                    ActionPlanStatus.FAILED,
                    ACTION_PLAN_TRANSITIONS,
                )

        raise

    transaction_id = new_id("txn")

    with session_scope() as session:
        plan = get_action_plan(
            session,
            plan_id,
            user.id,
        )

        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Action plan not found",
            )

        plan.approval_status = transition(
            plan.approval_status,
            ActionPlanStatus.APPROVED,
            ACTION_PLAN_TRANSITIONS,
        )

        transaction = Transaction(
            id=transaction_id,
            user_id=user.id,
            action_plan_id=plan_id,
            bmoni_proposal_id=proposal_id,
            amount_minor=snapshot[0],
            currency=snapshot[1],
            status=TransactionStatus.PENDING_SIGNATURE,
            bmoni_status="PENDING_SIGNATURES",
            idempotency_key=idempotency_key,
            created_at=utc_now(),
        )

        session.add(transaction)

        add_audit(
            session,
            event_id=new_id("aud"),
            actor_user_id=user.id,
            action="ACTION_PLAN_APPROVE",
            resource_type="TRANSACTION",
            resource_id=transaction_id,
            outcome="PENDING_SIGNATURE",
        )

    return {
        "id": transaction_id,
        "action_plan_id": plan_id,
        "bmoni_proposal_id": proposal_id,
        "status": TransactionStatus.PENDING_SIGNATURE,
        "money_has_moved": False,
    }


def owned_transaction(
    transaction_id: str,
    user_id: str,
) -> Transaction:
    """Load a transaction while enforcing ownership."""
    with session_scope() as session:
        item = get_transaction(
            session,
            transaction_id,
            user_id,
        )

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found",
            )

        session.expunge(item)
        return item


@app.get("/v1/transactions/{transaction_id}")
def read_transaction(
    transaction_id: str,
    user: User = Depends(current_user),
) -> dict:
    """Return a user's transaction."""
    return model_dict(
        owned_transaction(
            transaction_id,
            user.id,
        )
    )


@app.get("/v1/transactions/{transaction_id}/signing-payload")
def transaction_signing_payload(
    transaction_id: str,
    user: User = Depends(current_user),
) -> dict:
    """Return the BMONI signing payload for a pending transaction."""
    item = owned_transaction(
        transaction_id,
        user.id,
    )

    if item.status != TransactionStatus.PENDING_SIGNATURE:
        raise HTTPException(
            status_code=409,
            detail="Transaction is not awaiting a signature",
        )

    if not user.bmoni_user_id:
        raise HTTPException(
            status_code=409,
            detail="BMONI user provisioning is incomplete",
        )

    result = bmoni.get_proposal_signing_payload(
        bmoni_user_id=user.bmoni_user_id,
        proposal_id=item.bmoni_proposal_id,
    )
    return result["data"]


@app.post("/v1/transactions/{transaction_id}/signature")
def submit_transaction_signature(
    transaction_id: str,
    payload: SignatureRequest,
    request: Request,
    user: User = Depends(current_user),
) -> dict:
    """Submit a signature for a pending BMONI withdrawal proposal."""
    enforce_rate_limit(
        request,
        scope=f"financial-signature:{user.id}",
        limit=settings.financial_rate_limit_per_minute,
        window_seconds=60,
    )

    item = owned_transaction(
        transaction_id,
        user.id,
    )

    if item.status != TransactionStatus.PENDING_SIGNATURE:
        raise HTTPException(
            status_code=409,
            detail="Transaction is not awaiting a signature",
        )

    if not user.bmoni_user_id:
        raise HTTPException(
            status_code=409,
            detail="BMONI user provisioning is incomplete",
        )

    remote = bmoni.submit_proposal_signature(
        bmoni_user_id=user.bmoni_user_id,
        proposal_id=item.bmoni_proposal_id,
        signature=payload.signature,
    )

    remote_status = remote["data"]["proposal"]["status"]

    with session_scope() as session:
        transaction = get_transaction(
            session,
            transaction_id,
            user.id,
        )

        if not transaction:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found",
            )

        transaction.bmoni_status = remote_status

        if remote_status == "COMPLETED":
            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = utc_now()

        elif remote_status == "FAILED":
            transaction.status = TransactionStatus.FAILED

        else:
            transaction.status = TransactionStatus.PROCESSING

        add_audit(
            session,
            event_id=new_id("aud"),
            actor_user_id=user.id,
            action="TRANSACTION_SIGNATURE_SUBMIT",
            resource_type="TRANSACTION",
            resource_id=transaction_id,
            outcome=transaction.status,
        )

        return model_dict(transaction)


@app.patch("/v1/transactions/{transaction_id}/category")
def categorize_transaction(
    transaction_id: str,
    payload: TransactionCategorizeRequest,
    user: User = Depends(current_user),
) -> dict:
    """Assign a normalized category to a user's transaction."""
    with session_scope() as session:
        transaction = get_transaction(
            session,
            transaction_id,
            user.id,
        )

        if not transaction:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found",
            )

        transaction.category = payload.category.strip().lower()

        session.flush()

        return model_dict(transaction)


def get_authoritative_wallet_balance(
    user: User,
    currency: str,
) -> int:
    """Return the authoritative wallet balance from the BMONI balance service."""
    if not user.bmoni_user_id:
        raise HTTPException(
            status_code=409,
            detail="BMONI user provisioning is incomplete",
        )

    return available_balance_minor(
        bmoni,
        bmoni_user_id=user.bmoni_user_id,
        currency=currency,
    )


def validate_pocket_allocation(
    session,
    user_id: str,
    currency: str,
    requested_allocation_minor: int,
    wallet_balance_minor: int,
    exclude_pocket_id: str | None = None,
) -> None:
    """Reject an aggregate pocket allocation above authoritative balance."""
    statement = select(
        func.coalesce(
            func.sum(Pocket.allocated_minor),
            0,
        )
    ).where(
        Pocket.user_id == user_id,
        Pocket.currency == currency,
    )

    if exclude_pocket_id:
        statement = statement.where(
            Pocket.id != exclude_pocket_id
        )

    existing_allocated_minor = int(
        session.scalar(statement) or 0
    )

    total_allocated_minor = (
        existing_allocated_minor
        + requested_allocation_minor
    )

    if total_allocated_minor > wallet_balance_minor:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "POCKET_ALLOCATION_EXCEEDS_BALANCE",
                "message": (
                    "Total pocket allocation exceeds "
                    "the authoritative wallet balance"
                ),
                "currency": currency,
                "requested_allocation_minor": (
                    requested_allocation_minor
                ),
                "existing_allocated_minor": (
                    existing_allocated_minor
                ),
                "wallet_balance_minor": wallet_balance_minor,
            },
        )


@app.post("/v1/pockets", status_code=201)
def create_pocket(
    payload: PocketCreateRequest,
    user: User = Depends(current_user),
) -> dict:
    """Create a user-owned pocket after allocation validation."""
    currency = payload.currency.upper()

    if currency not in SUPPORTED_POCKET_CURRENCIES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNSUPPORTED_CURRENCY",
                "message": "Pocket currency is not supported",
            },
        )

    wallet_balance_minor = get_authoritative_wallet_balance(
        user,
        currency,
    )

    with session_scope() as session:
        validate_pocket_allocation(
            session=session,
            user_id=user.id,
            currency=currency,
            requested_allocation_minor=payload.allocated_minor,
            wallet_balance_minor=wallet_balance_minor,
        )

        pocket = Pocket(
            id=new_id("pocket"),
            user_id=user.id,
            name=payload.name.strip(),
            purpose=payload.purpose.strip(),
            allocated_minor=payload.allocated_minor,
            spent_minor=0,
            currency=currency,
            protected=payload.protected,
            created_at=utc_now(),
        )

        session.add(pocket)

        try:
            session.flush()
        except IntegrityError:
            raise HTTPException(
                status_code=409,
                detail="A pocket with this name already exists",
            )

        return _pocket_summary(pocket)


@app.get("/v1/pockets")
def list_pockets(
    user: User = Depends(current_user),
) -> list[dict]:
    """List all pockets owned by the authenticated user."""
    with session_scope() as session:
        return [
            _pocket_summary(item)
            for item in list_user_pockets(
                session,
                user.id,
            )
        ]


@app.get("/v1/pockets/{pocket_id}")
def read_pocket(
    pocket_id: str,
    user: User = Depends(current_user),
) -> dict:
    """Return one user-owned pocket."""
    with session_scope() as session:
        pocket = get_pocket_record(
            session,
            pocket_id,
            user.id,
        )

        if not pocket:
            raise HTTPException(
                status_code=404,
                detail="Pocket not found",
            )

        return _pocket_summary(pocket)


@app.patch("/v1/pockets/{pocket_id}")
def update_pocket(
    pocket_id: str,
    payload: PocketCreateRequest,
    user: User = Depends(current_user),
) -> dict:
    """Update a user-owned pocket while preserving spending history."""
    currency = payload.currency.upper()

    if currency not in SUPPORTED_POCKET_CURRENCIES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNSUPPORTED_CURRENCY",
                "message": "Pocket currency is not supported",
            },
        )

    wallet_balance_minor = get_authoritative_wallet_balance(
        user,
        currency,
    )

    with session_scope() as session:
        pocket = get_pocket_record(
            session,
            pocket_id,
            user.id,
        )

        if not pocket:
            raise HTTPException(
                status_code=404,
                detail="Pocket not found",
            )

        if payload.allocated_minor < pocket.spent_minor:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Pocket allocation cannot be below "
                    "the amount already spent"
                ),
            )

        validate_pocket_allocation(
            session=session,
            user_id=user.id,
            currency=currency,
            requested_allocation_minor=payload.allocated_minor,
            wallet_balance_minor=wallet_balance_minor,
            exclude_pocket_id=pocket.id,
        )

        pocket.name = payload.name.strip()
        pocket.purpose = payload.purpose.strip()
        pocket.allocated_minor = payload.allocated_minor
        pocket.currency = currency
        pocket.protected = payload.protected

        try:
            session.flush()
        except IntegrityError:
            raise HTTPException(
                status_code=409,
                detail="A pocket with this name already exists",
            )

        return _pocket_summary(pocket)


@app.delete("/v1/pockets/{pocket_id}", status_code=204)
def delete_pocket(
    pocket_id: str,
    user: User = Depends(current_user),
) -> None:
    """Delete a user-owned pocket that has no spending history."""
    with session_scope() as session:
        pocket = get_pocket_record(
            session,
            pocket_id,
            user.id,
        )

        if not pocket:
            raise HTTPException(
                status_code=404,
                detail="Pocket not found",
            )

        if pocket.spent_minor > 0:
            raise HTTPException(
                status_code=409,
                detail="A pocket with spending history cannot be deleted",
            )

        session.delete(pocket)


@app.post("/v1/pockets/transfer")
def transfer_pocket(
    payload: PocketTransferRequest,
    user: User = Depends(current_user),
) -> dict:
    """Transfer allocated funds between two pockets owned by the same user."""
    if (
        payload.source_pocket_id
        == payload.destination_pocket_id
    ):
        raise HTTPException(
            status_code=422,
            detail="Source and destination pockets must be different",
        )

    with session_scope() as session:
        source = get_pocket_record(
            session,
            payload.source_pocket_id,
            user.id,
        )
        destination = get_pocket_record(
            session,
            payload.destination_pocket_id,
            user.id,
        )

        if source is None or destination is None:
            raise HTTPException(
                status_code=404,
                detail="Source or destination pocket not found",
            )

        if source.currency != destination.currency:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CURRENCY_MISMATCH",
                    "message": (
                        "Pocket transfers must use "
                        "the same currency"
                    ),
                },
            )

        source_available_minor = (
            source.allocated_minor
            - source.spent_minor
        )

        if payload.amount_minor > source_available_minor:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INSUFFICIENT_POCKET_BALANCE",
                    "message": (
                        "Source pocket does not have "
                        "enough available balance"
                    ),
                    "available_minor": source_available_minor,
                    "requested_minor": payload.amount_minor,
                },
            )

        new_source_allocation = (
            source.allocated_minor
            - payload.amount_minor
        )

        new_destination_allocation = (
            destination.allocated_minor
            + payload.amount_minor
        )

        if new_source_allocation < source.spent_minor:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Transfer would reduce the source "
                    "allocation below its spent amount"
                ),
            )

        source.allocated_minor = new_source_allocation
        destination.allocated_minor = (
            new_destination_allocation
        )

        session.flush()

        return {
            "source": _pocket_summary(source),
            "destination": _pocket_summary(destination),
            "amount_minor": payload.amount_minor,
        }


@app.post(
    "/v1/recommendations/currency-shield",
    status_code=201,
)
def create_currency_shield(
    payload: CurrencyShieldRequest,
    user: User = Depends(current_user),
) -> dict:
    """Create a Currency Shield recommendation without moving money."""
    with session_scope() as session:
        pocket = get_pocket_record(
            session,
            payload.pocket_id,
            user.id,
        )

        if not pocket:
            raise HTTPException(
                status_code=404,
                detail="Pocket not found",
            )

        available = (
            pocket.allocated_minor
            - pocket.spent_minor
        )

        maximum = (
            available
            * settings.max_fx_conversion_percent
            // 100
        )

        if pocket.protected:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "PROTECTED_POCKET",
                    "message": (
                        "Protected pockets cannot fund "
                        "Currency Shield"
                    ),
                },
            )

        reasons = []

        if (
            pocket.currency != "CNGN"
            or payload.target_currency.upper() != "USD"
        ):
            reasons.append("UNSUPPORTED_PAIR")

        if payload.amount_minor > maximum:
            reasons.append(
                "AMOUNT_EXCEEDS_SAFETY_LIMIT"
            )

        if (
            payload.observed_change_bps
            > -settings.fx_alert_threshold_bps
        ):
            reasons.append(
                "ALERT_THRESHOLD_NOT_REACHED"
            )

        if reasons:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "NOT_RECOMMENDED",
                    "reasons": reasons,
                },
            )

        recommendation_id = new_id("rec")

        evidence = {
            "observed_change_bps": (
                payload.observed_change_bps
            ),
            "observation_window_days": (
                payload.observation_window_days
            ),
            "max_conversion_percent": (
                settings.max_fx_conversion_percent
            ),
        }

        rationale = (
            f"CNGN changed "
            f"{abs(payload.observed_change_bps) / 100:.2f}% "
            f"over {payload.observation_window_days} days. "
            "Consider diversifying part of this pocket."
        )

        disclosure = (
            "Rates can move in either direction. "
            "Conversion may include fees or spread. "
            "No money moves without approval."
        )

        session.add(
            Recommendation(
                id=recommendation_id,
                user_id=user.id,
                pocket_id=pocket.id,
                type="CURRENCY_SHIELD",
                status="AWAITING_APPROVAL",
                source_currency=pocket.currency,
                target_currency=payload.target_currency.upper(),
                amount_minor=payload.amount_minor,
                rationale=rationale,
                risk_disclosure=disclosure,
                evidence_json=json.dumps(evidence),
                created_at=utc_now(),
            )
        )

    return {
        "id": recommendation_id,
        "status": "AWAITING_APPROVAL",
        "rationale": rationale,
        "risk_disclosure": disclosure,
        "evidence": evidence,
        "requires_user_approval": True,
    }


@app.post(
    "/v1/recommendations/{recommendation_id}/approve",
    status_code=201,
)
def approve_currency_shield(
    recommendation_id: str,
    request: Request,
    idempotency_key: str = Header(
        min_length=8,
        max_length=128,
        alias="Idempotency-Key",
    ),
    user: User = Depends(current_user),
) -> dict:
    """Approve a Currency Shield recommendation and create a signing proposal."""
    enforce_rate_limit(
        request,
        scope=f"financial-fx:{user.id}",
        limit=settings.financial_rate_limit_per_minute,
        window_seconds=60,
    )

    with session_scope() as session:
        existing = get_fx_by_idempotency(
            session,
            user.id,
            idempotency_key,
        )

        if existing:
            return {
                "id": existing.id,
                "bmoni_proposal_id": (
                    existing.bmoni_conversion_id
                ),
                "status": existing.status,
                "quote": json.loads(
                    existing.quote_json
                ),
                "money_has_moved": (
                    existing.status == "COMPLETED"
                ),
            }

        wallet = get_wallet_by_user(
            session,
            user.id,
        )

        if (
            not wallet
            or not wallet.bmoni_wallet_id
            or not user.bmoni_user_id
        ):
            raise HTTPException(
                status_code=409,
                detail="A managed BMONI wallet is required",
            )

        recommendation = session.scalar(
            select(Recommendation)
            .where(
                Recommendation.id == recommendation_id,
                Recommendation.user_id == user.id,
            )
            .with_for_update()
        )

        if not recommendation:
            raise HTTPException(
                status_code=404,
                detail="Recommendation not found",
            )

        if (
            recommendation.status
            != RecommendationStatus.AWAITING_APPROVAL
        ):
            raise HTTPException(
                status_code=409,
                detail="Recommendation cannot be approved",
            )

        recommendation.status = transition(
            recommendation.status,
            RecommendationStatus.EXECUTING,
            RECOMMENDATION_TRANSITIONS,
        )

        snapshot = (
            recommendation.amount_minor,
            recommendation.source_currency,
            recommendation.target_currency,
            user.bmoni_user_id,
            wallet.bmoni_wallet_id,
        )

    if (
        snapshot[0] is None
        or snapshot[1] is None
        or snapshot[2] is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Recommendation is incomplete",
        )

    try:
        balance = available_balance_minor(
            bmoni,
            bmoni_user_id=snapshot[3],
            currency=snapshot[1],
        )

        if snapshot[0] > balance:
            raise HTTPException(
                status_code=422,
                detail="Insufficient authoritative wallet balance",
            )

        quote = bmoni.get_fx_quote(
            bmoni_user_id=snapshot[3],
            amount_decimal=minor_to_decimal(
                snapshot[0],
                "NGN",
            ),
            source="NGN",
            target=snapshot[2],
        )

        created = bmoni.create_swap_proposal(
            bmoni_user_id=snapshot[3],
            smart_wallet_id=snapshot[4],
            amount_decimal=minor_to_decimal(
                snapshot[0],
                snapshot[1],
            ),
            from_stablecoin=snapshot[1],
            to_stablecoin=(
                "USDB"
                if snapshot[2] == "USD"
                else snapshot[2]
            ),
        )

        proposal_id = (
            created["data"]["proposal"]["id"]
        )

        approved = bmoni.approve_proposal(
            bmoni_user_id=snapshot[3],
            proposal_id=proposal_id,
        )

        remote_status = (
            approved["data"]["proposal"]["status"]
        )

        if remote_status != "PENDING_SIGNATURES":
            raise BmoniError(
                "BMONI proposal is not ready for signing",
                code="BMONI_UNEXPECTED_PROPOSAL_STATUS",
            )

    except Exception as exc:
        ambiguous = (
            isinstance(exc, BmoniError)
            and exc.retryable
        )

        with session_scope() as session:
            failed_recommendation = get_recommendation(
                session,
                recommendation_id,
                user.id,
            )

            if (
                not ambiguous
                and failed_recommendation
                and failed_recommendation.status
                == RecommendationStatus.EXECUTING
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
        recommendation = get_recommendation(
            session,
            recommendation_id,
            user.id,
        )

        if not recommendation:
            raise HTTPException(
                status_code=404,
                detail="Recommendation not found",
            )

        session.add(
            FxConversion(
                id=conversion_id,
                user_id=user.id,
                recommendation_id=recommendation_id,
                bmoni_conversion_id=proposal_id,
                status="PENDING_SIGNATURE",
                source_amount_minor=snapshot[0],
                source_currency=snapshot[1],
                target_currency=snapshot[2],
                quote_json=json.dumps(quote),
                idempotency_key=idempotency_key,
                created_at=utc_now(),
                completed_at=None,
            )
        )

        add_audit(
            session,
            event_id=new_id("aud"),
            actor_user_id=user.id,
            action="FX_CONVERSION_APPROVE",
            resource_type="FX_CONVERSION",
            resource_id=conversion_id,
            outcome="PENDING_SIGNATURE",
        )

    return {
        "id": conversion_id,
        "bmoni_proposal_id": proposal_id,
        "status": "PENDING_SIGNATURE",
        "quote": quote,
        "money_has_moved": False,
    }


def _reconcile_fx(
    conversion: FxConversion,
    recommendation: Recommendation,
    remote: dict,
) -> None:
    """Map the remote BMONI proposal status into local workflow state."""
    remote_status = remote["data"]["proposal"]["status"]

    status_map = {
        "PENDING_APPROVALS": "PROCESSING",
        "PENDING_SIGNATURES": "PENDING_SIGNATURE",
        "COMPLETED": "COMPLETED",
        "FAILED": "FAILED",
    }

    conversion.status = status_map.get(
        remote_status,
        "PROCESSING",
    )

    if (
        conversion.status == "COMPLETED"
        and recommendation.status
        == RecommendationStatus.EXECUTING
    ):
        recommendation.status = transition(
            recommendation.status,
            RecommendationStatus.EXECUTED,
            RECOMMENDATION_TRANSITIONS,
        )

        conversion.completed_at = utc_now()

    elif (
        conversion.status == "FAILED"
        and recommendation.status
        == RecommendationStatus.EXECUTING
    ):
        recommendation.status = transition(
            recommendation.status,
            RecommendationStatus.FAILED,
            RECOMMENDATION_TRANSITIONS,
        )


@app.get("/v1/fx/conversions/{conversion_id}")
def get_currency_shield_conversion(
    conversion_id: str,
    user: User = Depends(current_user),
) -> dict:
    """Return and reconcile a Currency Shield conversion."""
    with session_scope() as session:
        conversion = get_fx_conversion(
            session,
            conversion_id,
            user.id,
        )

        if not conversion:
            raise HTTPException(
                status_code=404,
                detail="Conversion not found",
            )

        recommendation = get_recommendation(
            session,
            conversion.recommendation_id,
            user.id,
        )

        if not recommendation:
            raise HTTPException(
                status_code=404,
                detail="Recommendation not found",
            )

        remote = bmoni.get_proposal(
            bmoni_user_id=user.bmoni_user_id or "",
            proposal_id=conversion.bmoni_conversion_id,
        )

        _reconcile_fx(
            conversion,
            recommendation,
            remote,
        )

        return {
            "id": conversion.id,
            "bmoni_proposal_id": (
                conversion.bmoni_conversion_id
            ),
            "status": conversion.status,
            "money_has_moved": (
                conversion.status == "COMPLETED"
            ),
        }


@app.get(
    "/v1/fx/conversions/{conversion_id}/signing-payload"
)
def currency_shield_signing_payload(
    conversion_id: str,
    user: User = Depends(current_user),
) -> dict:
    """Return the BMONI signing payload for a Currency Shield conversion."""
    with session_scope() as session:
        conversion = get_fx_conversion(
            session,
            conversion_id,
            user.id,
        )

        if not conversion:
            raise HTTPException(
                status_code=404,
                detail="Conversion not found",
            )

        if conversion.status != "PENDING_SIGNATURE":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Conversion is not awaiting "
                    "a signature"
                ),
            )

        proposal_id = conversion.bmoni_conversion_id

    result = bmoni.get_proposal_signing_payload(
        bmoni_user_id=user.bmoni_user_id or "",
        proposal_id=proposal_id,
    )

    return result["data"]


@app.post(
    "/v1/fx/conversions/{conversion_id}/signature"
)
def submit_currency_shield_signature(
    conversion_id: str,
    payload: ProposalSignatureRequest,
    request: Request,
    user: User = Depends(current_user),
) -> dict:
    """Submit a signature for a Currency Shield proposal."""
    enforce_rate_limit(
        request,
        scope=f"financial-fx-signature:{user.id}",
        limit=settings.financial_rate_limit_per_minute,
        window_seconds=60,
    )

    with session_scope() as session:
        conversion = get_fx_conversion(
            session,
            conversion_id,
            user.id,
        )

        if not conversion:
            raise HTTPException(
                status_code=404,
                detail="Conversion not found",
            )

        if conversion.status != "PENDING_SIGNATURE":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Conversion is not awaiting "
                    "a signature"
                ),
            )

        proposal_id = conversion.bmoni_conversion_id

    remote = bmoni.submit_proposal_signature(
        bmoni_user_id=user.bmoni_user_id or "",
        proposal_id=proposal_id,
        signature=payload.signature,
    )

    with session_scope() as session:
        conversion = get_fx_conversion(
            session,
            conversion_id,
            user.id,
        )

        if not conversion:
            raise HTTPException(
                status_code=404,
                detail="Conversion not found",
            )

        recommendation = get_recommendation(
            session,
            conversion.recommendation_id,
            user.id,
        )

        if not recommendation:
            raise HTTPException(
                status_code=404,
                detail="Recommendation not found",
            )

        _reconcile_fx(
            conversion,
            recommendation,
            remote,
        )

        add_audit(
            session,
            event_id=new_id("aud"),
            actor_user_id=user.id,
            action="FX_SIGNATURE_SUBMIT",
            resource_type="FX_CONVERSION",
            resource_id=conversion_id,
            outcome=conversion.status,
        )

        return {
            "id": conversion.id,
            "bmoni_proposal_id": proposal_id,
            "status": conversion.status,
            "money_has_moved": (
                conversion.status == "COMPLETED"
            ),
        }


@app.post("/v1/webhooks/bmoni")
async def bmoni_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(
        default=None,
        alias="X-Webhook-Signature",
    ),
    x_webhook_id: str | None = Header(
        default=None,
        alias="X-Webhook-Id",
    ),
    x_source_event_id: str | None = Header(
        default=None,
        alias="X-Source-Event-Id",
    ),
) -> dict:
    """Process an idempotent BMONI webhook event."""
    body = await request.body()

    expected_signature = hmac.new(
        settings.bmoni_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not x_webhook_signature or not hmac.compare_digest(
        expected_signature,
        x_webhook_signature,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook payload",
        )

    event_id = payload.get("id")

    if not event_id:
        raise HTTPException(
            status_code=400,
            detail="Webhook event id is required",
        )

    if (
        x_webhook_id
        and x_webhook_id != event_id
    ):
        raise HTTPException(
            status_code=422,
            detail="Webhook ID header does not match body",
        )

    event_type = payload.get(
        "eventType",
        "UNKNOWN",
    )

    event_payload = payload.get(
        "payload",
        {},
    )

    proposal_id = (
        event_payload.get("proposalId")
        or event_payload.get("proposal_id")
        or event_payload.get("withdrawalId")
    )

    remote_status = (
        event_payload.get("status")
        or payload.get("status")
    )

    with session_scope() as session:
        existing = get_webhook_event(
            session,
            event_id,
        )

        if existing:
            return {
                "received": True,
                "duplicate": True,
            }

        session.add(
            WebhookEvent(
                id=event_id,
                event_type=event_type,
                external_id=x_source_event_id or event_id,
                payload_json=body.decode(
                    "utf-8",
                    errors="replace",
                ),
                processed=False,
                created_at=utc_now(),
            )
        )

        if proposal_id:
            transaction = get_transaction_by_proposal(
                session,
                proposal_id,
            )

            if transaction:
                transaction.bmoni_status = (
                    remote_status
                    or transaction.bmoni_status
                )

                if remote_status == "COMPLETED":
                    transaction.status = (
                        TransactionStatus.COMPLETED
                    )
                    transaction.completed_at = utc_now()

                elif remote_status == "FAILED":
                    transaction.status = (
                        TransactionStatus.FAILED
                    )

                else:
                    transaction.status = (
                        TransactionStatus.PROCESSING
                    )

        event = get_webhook_event(
            session,
            event_id,
        )

        if event:
            event.processed = True

    return {
        "received": True,
        "duplicate": False,
    }


@app.get(
    "/v1/investment-opportunities",
    response_model=list[InvestmentOpportunityResponse],
)
def list_investment_opportunities(
    user: User = Depends(current_user),
) -> list[dict]:
    """Return verified investment opportunities as read-only information."""
    # Investment opportunities are intentionally not exposed as
    # executable financial actions in Task B.
    #
    # The current origin/main models.py does not define an
    # InvestmentOpportunity model, so this endpoint is intentionally
    # left unavailable until the corresponding Alembic model/migration
    # is added rather than silently creating a second database schema.
    raise HTTPException(
        status_code=501,
        detail=(
            "Investment opportunity storage has not yet been "
            "added to the SQLAlchemy/Alembic model"
        ),
    )
