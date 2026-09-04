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
    ActionPlanRequest,
    CurrencyShieldRequest,
    InvestmentOpportunityResponse,
    LoginRequest,
    PocketCreateRequest,
    PocketTransferRequest,
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


# Seed the read-only investment opportunities for the demo environment.
def seed_investment_opportunities() -> None:
    """Create demo investment opportunities when the table is empty."""

    # Insert demo opportunities only once.
    with connection() as conn:
        existing = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM investment_opportunities
            """
        ).fetchone()

        if existing["count"] > 0:
            return

        # Store informational opportunities without any execution mechanism.
        opportunities = [
            (
                new_id("inv"),
                "Verified Treasury Fund",
                "Demo Regulated Provider",
                "VERIFIED",
                "LOW",
                "DAILY",
                0,
                "CNGN",
                "Read-only demo investment opportunity for the Innovation Fair.",
                now_iso(),
            ),
            (
                new_id("inv"),
                "Balanced Growth Fund",
                "Demo Regulated Provider",
                "VERIFIED",
                "MEDIUM",
                "WEEKLY",
                500,
                "CNGN",
                "Read-only demo opportunity with moderate risk.",
                now_iso(),
            ),
        ]

        conn.executemany(
            """
            INSERT INTO investment_opportunities
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            opportunities,
        )


# Initialize the database and demo data when the FastAPI application starts.
@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize application storage and demo fixtures during startup."""

    # Create all application tables before serving requests.
    init_db()

    # Seed the read-only investment opportunities for the demo environment.
    seed_investment_opportunities()

    yield


app = FastAPI(
    title="FlowPilot API",
    version="0.1.0",
    lifespan=lifespan,
)

bearer = HTTPBearer(auto_error=False)


# Generate internal identifiers using a readable resource prefix.
def new_id(prefix: str) -> str:
    """Return a unique identifier prefixed with the resource type."""

    return f"{prefix}_{uuid.uuid4().hex}"


# Resolve the authenticated FlowPilot user from the bearer access token.
def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """Return the authenticated user or reject the request."""

    # Require a bearer token for protected endpoints.
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    try:
        # Decode and validate the access token.
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
        )

    # Load the user associated with the token.
    with connection() as conn:
        user = row_dict(
            conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        )

    # Reject tokens belonging to users that no longer exist.
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User no longer exists",
        )

    return user


# Convert BMONI configuration failures into a consistent API response.
@app.exception_handler(BmoniConfigurationError)
async def bmoni_config_error(
    _: Request,
    exc: BmoniConfigurationError,
):
    """Return a service-unavailable response for BMONI configuration errors."""

    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
    )


# Provide a lightweight health check for the application.
@app.get("/health")
def health() -> dict:
    """Return the API health status and active BMONI mode."""

    return {
        "status": "ok",
        "bmoni_mode": settings.bmoni_mode,
    }


# Register a new FlowPilot user and provision the corresponding BMONI user.
@app.post("/v1/auth/register", status_code=201)
def register(payload: RegisterRequest) -> dict:
    """Create a FlowPilot account and its BMONI user."""

    user_id = new_id("usr")

    # Reject duplicate local accounts before calling BMONI.
    with connection() as conn:
        if conn.execute(
            "SELECT 1 FROM users WHERE email = ?",
            (str(payload.email).lower(),),
        ).fetchone():
            raise HTTPException(
                status_code=409,
                detail="A FlowPilot account with this email already exists",
            )

    try:
        # Provision the user in BMONI with the phone number required by its API.
        remote = bmoni.create_user(
            external_id=user_id,
            email=str(payload.email),
            name=payload.name,
            phone_number=payload.phone_number,
        )

        # Save the local account after BMONI provisioning succeeds.
        with connection() as conn:
            conn.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    str(payload.email).lower(),
                    payload.name,
                    hash_password(payload.password),
                    remote["id"],
                    now_iso(),
                ),
            )

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A FlowPilot account with this email already exists",
        )

    return {
        "access_token": create_access_token(user_id),
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": str(payload.email),
            "name": payload.name,
            "bmoni_user_id": remote["id"],
        },
    }


# Authenticate an existing FlowPilot user.
@app.post("/v1/auth/login")
def login(payload: LoginRequest) -> dict:
    """Authenticate a user and return an access token."""

    # Load the account by normalized email.
    with connection() as conn:
        user = row_dict(
            conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (str(payload.email).lower(),),
            ).fetchone()
        )

    # Reject invalid credentials without revealing which credential failed.
    if not user or not verify_password(
        payload.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    return {
        "access_token": create_access_token(user["id"]),
        "token_type": "bearer",
    }


# Return the authenticated user's profile.
@app.get("/v1/me")
def me(user: dict = Depends(current_user)) -> dict:
    """Return the current authenticated user's profile."""

    return {
        key: user[key]
        for key in (
            "id",
            "email",
            "name",
            "bmoni_user_id",
            "created_at",
        )
    }


# Link a CNGN wallet to the authenticated user.
@app.post("/v1/wallets/link", status_code=201)
def link_wallet(
    payload: WalletLinkRequest,
    user: dict = Depends(current_user),
) -> dict:
    """Link a supported wallet to the authenticated user."""

    currency = payload.currency.upper()

    # The current MVP only supports CNGN wallets.
    if currency != "CNGN":
        raise HTTPException(
            status_code=422,
            detail="The MVP currently supports CNGN only",
        )

    # Ask BMONI to link the wallet.
    remote = bmoni.link_wallet(
        bmoni_user_id=user["bmoni_user_id"],
        address=payload.wallet_address,
        currency=currency,
    )

    wallet_id = new_id("wal")

    try:
        # Save the linked wallet locally.
        with connection() as conn:
            conn.execute(
                "INSERT INTO wallets VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    wallet_id,
                    user["id"],
                    remote["id"],
                    payload.wallet_address,
                    currency,
                    remote["status"],
                    now_iso(),
                ),
            )

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="This user or wallet address is already linked",
        )

    return {
        "id": wallet_id,
        "bmoni_wallet_id": remote["id"],
        "status": remote["status"],
        "currency": currency,
    }


# Create a risk-checked action plan before any money movement.
@app.post("/v1/action-plans", status_code=201)
def create_action_plan(
    payload: ActionPlanRequest,
    user: dict = Depends(current_user),
) -> dict:
    """Create a withdrawal action plan after applying risk checks."""

    currency = payload.currency.upper()
    failures = []

    # Reject currencies unsupported by the current MVP.
    if currency != "CNGN":
        failures.append("UNSUPPORTED_CURRENCY")

    # Reject withdrawals larger than the supplied available balance.
    if payload.amount_minor > payload.available_balance_minor:
        failures.append("INSUFFICIENT_BALANCE")

    # Enforce the application-level transaction limit.
    if payload.amount_minor > settings.max_transaction_minor:
        failures.append("PER_TRANSACTION_LIMIT_EXCEEDED")

    # Return all detected risk failures together.
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
        payload.available_balance_minor - payload.amount_minor
    )

    # Store the action plan without moving money.
    with connection() as conn:
        conn.execute(
            "INSERT INTO action_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                plan_id,
                user["id"],
                "BANK_WITHDRAWAL",
                payload.amount_minor,
                currency,
                payload.recipient_name,
                payload.message,
                payload.available_balance_minor,
                expected,
                "PASSED",
                "AWAITING_USER_APPROVAL",
                now_iso(),
            ),
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


# Approve an action plan and create the corresponding BMONI withdrawal proposal.
@app.post("/v1/action-plans/{plan_id}/approve", status_code=201)
def approve_action_plan(
    plan_id: str,
    idempotency_key: str = Header(
        min_length=8,
        max_length=128,
        alias="Idempotency-Key",
    ),
    user: dict = Depends(current_user),
) -> dict:
    """Approve a withdrawal action plan idempotently."""

    with connection() as conn:
        # Return an existing transaction for a repeated idempotency key.
        existing = row_dict(
            conn.execute(
                """
                SELECT *
                FROM transactions
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (user["id"], idempotency_key),
            ).fetchone()
        )

        if existing:
            return existing

        # Load the action plan while enforcing ownership.
        plan = row_dict(
            conn.execute(
                """
                SELECT *
                FROM action_plans
                WHERE id = ? AND user_id = ?
                """,
                (plan_id, user["id"]),
            ).fetchone()
        )

        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Action plan not found",
            )

        # Prevent an action plan from being approved twice.
        if plan["approval_status"] != "AWAITING_USER_APPROVAL":
            raise HTTPException(
                status_code=409,
                detail="Action plan cannot be approved in its current state",
            )

        # Create the BMONI withdrawal proposal after explicit user approval.
        proposal = bmoni.create_withdrawal_proposal(
            bmoni_user_id=user["bmoni_user_id"],
            amount_minor=plan["amount_minor"],
            currency=plan["currency"],
            recipient_name=plan["recipient_name"],
        )

        transaction_id = new_id("txn")

        # Mark the action plan approved and store the pending transaction.
        conn.execute(
            """
            UPDATE action_plans
            SET approval_status = 'APPROVED'
            WHERE id = ?
            """,
            (plan_id,),
        )

        conn.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                transaction_id,
                user["id"],
                plan_id,
                proposal["id"],
                plan["amount_minor"],
                plan["currency"],
                "PENDING_SIGNATURE",
                proposal["status"],
                idempotency_key,
                now_iso(),
            ),
        )

    return {
        "id": transaction_id,
        "bmoni_proposal_id": proposal["id"],
        "status": "PENDING_SIGNATURE",
    }


# Load a transaction while enforcing ownership.
def owned_transaction(
    transaction_id: str,
    user_id: str,
) -> dict:
    """Return a transaction belonging to the supplied user."""

    with connection() as conn:
        transaction = row_dict(
            conn.execute(
                """
                SELECT *
                FROM transactions
                WHERE id = ? AND user_id = ?
                """,
                (transaction_id, user_id),
            ).fetchone()
        )

    if not transaction:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found",
        )

    return transaction


# Return one transaction owned by the authenticated user.
@app.get("/v1/transactions/{transaction_id}")
def get_transaction(
    transaction_id: str,
    user: dict = Depends(current_user),
) -> dict:
    """Return an authenticated user's transaction."""

    return owned_transaction(transaction_id, user["id"])


# Return the BMONI signing payload for a pending transaction.
@app.get("/v1/transactions/{transaction_id}/signing-payload")
def signing_payload(
    transaction_id: str,
    user: dict = Depends(current_user),
) -> dict:
    """Return the signing payload for a pending transaction."""

    transaction = owned_transaction(
        transaction_id,
        user["id"],
    )

    if transaction["status"] != "PENDING_SIGNATURE":
        raise HTTPException(
            status_code=409,
            detail="Transaction is not awaiting a signature",
        )

    return bmoni.get_signing_payload(
        proposal_id=transaction["bmoni_proposal_id"]
    )


# Submit a user signature to BMONI for a pending transaction.
@app.post("/v1/transactions/{transaction_id}/signature")
def submit_signature(
    transaction_id: str,
    payload: SignatureRequest,
    user: dict = Depends(current_user),
) -> dict:
    """Submit a transaction signature and update its local status."""

    transaction = owned_transaction(
        transaction_id,
        user["id"],
    )

    if transaction["status"] != "PENDING_SIGNATURE":
        raise HTTPException(
            status_code=409,
            detail="Transaction is not awaiting a signature",
        )

    try:
        # Submit the user's signature to BMONI.
        remote = bmoni.submit_signature(
            proposal_id=transaction["bmoni_proposal_id"],
            signature=payload.signature,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    # Translate BMONI status into the local transaction status.
    local_status = (
        "COMPLETED"
        if remote["status"] == "COMPLETED"
        else "PROCESSING"
    )

    completed_at = (
        now_iso()
        if local_status == "COMPLETED"
        else None
    )

    # Persist the resulting transaction state.
    with connection() as conn:
        conn.execute(
            """
            UPDATE transactions
            SET status = ?, bmoni_status = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                local_status,
                remote["status"],
                completed_at,
                transaction_id,
            ),
        )

    return {
        "id": transaction_id,
        "status": local_status,
        "bmoni_status": remote["status"],
    }


# Categorize a transaction belonging to the authenticated user.
@app.patch("/v1/transactions/{transaction_id}/category")
def categorize_transaction(
    transaction_id: str,
    payload: TransactionCategorizeRequest,
    user: dict = Depends(current_user),
) -> dict:
    """Assign a category to a user's transaction."""

    # Load the transaction while enforcing ownership.
    with connection() as conn:
        transaction = conn.execute(
            """
            SELECT *
            FROM transactions
            WHERE id = ? AND user_id = ?
            """,
            (transaction_id, user["id"]),
        ).fetchone()

        # Prevent users from accessing another user's transaction.
        if transaction is None:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found",
            )

        # Save the normalized category.
        category = payload.category.strip().lower()

        conn.execute(
            """
            UPDATE transactions
            SET category = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                category,
                transaction_id,
                user["id"],
            ),
        )

        # Return the updated transaction.
        updated = conn.execute(
            """
            SELECT *
            FROM transactions
            WHERE id = ? AND user_id = ?
            """,
            (transaction_id, user["id"]),
        ).fetchone()

    return row_dict(updated)


# Receive asynchronous transaction status updates from BMONI.
@app.post("/v1/webhooks/bmoni")
async def bmoni_webhook(
    request: Request,
    x_bmoni_signature: str | None = Header(default=None),
) -> dict:
    """Process authenticated BMONI webhook events idempotently."""

    raw = await request.body()

    # Validate the webhook signature when a secret is configured.
    if settings.bmoni_webhook_secret:
        expected = hmac.new(
            settings.bmoni_webhook_secret.encode(),
            raw,
            hashlib.sha256,
        ).hexdigest()

        if not x_bmoni_signature or not hmac.compare_digest(
            x_bmoni_signature,
            expected,
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid webhook signature",
            )

    # Require a secret outside local development.
    elif settings.environment != "development":
        raise HTTPException(
            status_code=503,
            detail="Webhook secret is not configured",
        )

    try:
        # Parse the webhook payload.
        event = json.loads(raw)
        event_id = str(event["id"])
        event_type = str(event["type"])
        proposal_id = str(event["proposal_id"])
        remote_status = str(event["status"])

    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="Invalid webhook payload",
        )

    with connection() as conn:
        # Ignore already-processed webhook events.
        if conn.execute(
            "SELECT 1 FROM webhook_events WHERE id = ?",
            (event_id,),
        ).fetchone():
            return {
                "received": True,
                "duplicate": True,
            }

        # Translate remote BMONI statuses into local transaction statuses.
        mapping = {
            "COMPLETED": "COMPLETED",
            "FAILED": "FAILED",
            "PENDING": "PROCESSING",
        }

        local_status = mapping.get(
            remote_status,
            "PROCESSING",
        )

        completed_at = (
            now_iso()
            if local_status == "COMPLETED"
            else None
        )

        # Update the transaction associated with the BMONI proposal.
        conn.execute(
            """
            UPDATE transactions
            SET status = ?, bmoni_status = ?, completed_at = ?
            WHERE bmoni_proposal_id = ?
            """,
            (
                local_status,
                remote_status,
                completed_at,
                proposal_id,
            ),
        )

        # Record the event so duplicate webhooks are ignored.
        conn.execute(
            "INSERT INTO webhook_events VALUES (?, ?, ?, ?, 1, ?)",
            (
                event_id,
                event_type,
                proposal_id,
                json_text(event),
                now_iso(),
            ),
        )

    return {
        "received": True,
        "duplicate": False,
    }


# Provide the wallet balance used by pocket allocation validation.
def get_authoritative_wallet_balance(
    user: dict,
    currency: str,
) -> int:
    """Return the authoritative wallet balance in integer minor units.

    This temporary provider remains separate from pocket logic so the shared
    BMONI balance service can replace it without changing allocation validation.
    """

    # Return the temporary development balance until the BMONI balance service is connected.
    return 100_000_000


# Validate a pocket allocation against an authoritative backend balance.
def validate_pocket_allocation(
    user: dict,
    currency: str,
    requested_allocation_minor: int,
    wallet_balance_minor: int,
    exclude_pocket_id: str | None = None,
) -> None:
    """Reject an allocation when aggregate pocket allocations exceed wallet balance."""

    # Calculate the total amount already allocated to this user's pockets in this currency.
    with connection() as conn:
        if exclude_pocket_id:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(allocated_minor), 0) AS total_allocated_minor
                FROM pockets
                WHERE user_id = ?
                  AND currency = ?
                  AND id != ?
                """,
                (
                    user["id"],
                    currency,
                    exclude_pocket_id,
                ),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(allocated_minor), 0) AS total_allocated_minor
                FROM pockets
                WHERE user_id = ?
                  AND currency = ?
                """,
                (
                    user["id"],
                    currency,
                ),
            ).fetchone()

    # Keep all balance calculations in integer minor units.
    existing_allocated_minor = int(
        row["total_allocated_minor"]
    )

    # Calculate the aggregate allocation after applying the requested amount.
    total_allocated_minor = (
        existing_allocated_minor
        + requested_allocation_minor
    )

    # Reject the request when aggregate allocation exceeds the authoritative balance.
    if total_allocated_minor > wallet_balance_minor:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "POCKET_ALLOCATION_EXCEEDS_BALANCE",
                "message": (
                    "Total pocket allocation exceeds the "
                    "authoritative wallet balance"
                ),
                "currency": currency,
                "requested_allocation_minor": requested_allocation_minor,
                "existing_allocated_minor": existing_allocated_minor,
                "wallet_balance_minor": wallet_balance_minor,
            },
        )


# Create a pocket after validating its allocation against the authoritative wallet balance.
@app.post("/v1/pockets", status_code=201)
def create_pocket(
    payload: PocketCreateRequest,
    user: dict = Depends(current_user),
) -> dict:
    """Create a new spending pocket after validating its aggregate allocation."""

    # Normalize the currency before applying currency-specific validation.
    currency = payload.currency.upper()

    # Restrict pocket allocations to currencies currently supported by the application.
    if currency not in {"CNGN", "USD"}:
        raise HTTPException(
            status_code=422,
            detail="Unsupported pocket currency",
        )

    # Retrieve the authoritative balance from the backend balance provider.
    wallet_balance_minor = get_authoritative_wallet_balance(
        user=user,
        currency=currency,
    )

    # Validate the new allocation against all existing allocations in this currency.
    validate_pocket_allocation(
        user=user,
        currency=currency,
        requested_allocation_minor=payload.allocated_minor,
        wallet_balance_minor=wallet_balance_minor,
    )

    pocket_id = new_id("pkt")

    try:
        # Save the pocket only after all allocation checks have passed.
        with connection() as conn:
            conn.execute(
                "INSERT INTO pockets VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
                (
                    pocket_id,
                    user["id"],
                    payload.name,
                    payload.purpose,
                    payload.allocated_minor,
                    currency,
                    int(payload.protected),
                    now_iso(),
                ),
            )

    except sqlite3.IntegrityError:
        # Prevent duplicate pocket names for the same user.
        raise HTTPException(
            status_code=409,
            detail="A pocket with this name already exists",
        )

    return {
        "id": pocket_id,
        "name": payload.name,
        "purpose": payload.purpose,
        "allocated_minor": payload.allocated_minor,
        "spent_minor": 0,
        "available_minor": payload.allocated_minor,
        "currency": currency,
        "protected": payload.protected,
        "created_at": now_iso(),
    }


# Return all pockets owned by the authenticated user with calculated balances.
@app.get("/v1/pockets")
def list_pockets(
    user: dict = Depends(current_user),
) -> list[dict]:
    """Return every pocket owned by the authenticated user."""

    # Load only pockets belonging to the authenticated user.
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM pockets
            WHERE user_id = ?
            ORDER BY created_at
            """,
            (user["id"],),
        ).fetchall()

    # Convert each database row into the frontend pocket summary contract.
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "purpose": row["purpose"],
            "allocated_minor": row["allocated_minor"],
            "spent_minor": row["spent_minor"],
            "available_minor": (
                row["allocated_minor"]
                - row["spent_minor"]
            ),
            "currency": row["currency"],
            "protected": bool(row["protected"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


# Return one pocket owned by the authenticated user with its current balance summary.
@app.get("/v1/pockets/{pocket_id}")
def get_pocket(
    pocket_id: str,
    user: dict = Depends(current_user),
) -> dict:
    """Return a single pocket and its balance summary."""

    # Query by both pocket ID and user ID to enforce ownership.
    with connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM pockets
            WHERE id = ? AND user_id = ?
            """,
            (
                pocket_id,
                user["id"],
            ),
        ).fetchone()

    # Hide whether a pocket exists for another user.
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Pocket not found",
        )

    # Calculate the amount remaining in the pocket.
    available_minor = (
        row["allocated_minor"]
        - row["spent_minor"]
    )

    return {
        "id": row["id"],
        "name": row["name"],
        "purpose": row["purpose"],
        "allocated_minor": row["allocated_minor"],
        "spent_minor": row["spent_minor"],
        "available_minor": available_minor,
        "currency": row["currency"],
        "protected": bool(row["protected"]),
        "created_at": row["created_at"],
    }


# Update an editable pocket while preserving its spending history.
@app.patch("/v1/pockets/{pocket_id}")
def update_pocket(
    pocket_id: str,
    payload: PocketCreateRequest,
    user: dict = Depends(current_user),
) -> dict:
    """Update a user's pocket while preserving its current spending history."""

    # Normalize the requested currency before validation.
    currency = payload.currency.upper()

    # Restrict pockets to currently supported currencies.
    if currency not in {"CNGN", "USD"}:
        raise HTTPException(
            status_code=422,
            detail="Unsupported pocket currency",
        )

    # Load the pocket while enforcing ownership.
    with connection() as conn:
        pocket = conn.execute(
            """
            SELECT *
            FROM pockets
            WHERE id = ? AND user_id = ?
            """,
            (
                pocket_id,
                user["id"],
            ),
        ).fetchone()

    # Return not found when the pocket does not belong to the user.
    if not pocket:
        raise HTTPException(
            status_code=404,
            detail="Pocket not found",
        )

    # Do not reduce allocation below money already spent.
    if payload.allocated_minor < pocket["spent_minor"]:
        raise HTTPException(
            status_code=422,
            detail="Allocated amount cannot be less than the amount already spent",
        )

    # Retrieve the authoritative balance for the requested currency.
    wallet_balance_minor = get_authoritative_wallet_balance(
        user=user,
        currency=currency,
    )

    # Validate aggregate allocation while excluding the current pocket.
    validate_pocket_allocation(
        user=user,
        currency=currency,
        requested_allocation_minor=payload.allocated_minor,
        wallet_balance_minor=wallet_balance_minor,
        exclude_pocket_id=pocket_id,
    )

    try:
        # Update only this user's pocket.
        with connection() as conn:
            conn.execute(
                """
                UPDATE pockets
                SET name = ?,
                    purpose = ?,
                    allocated_minor = ?,
                    currency = ?,
                    protected = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    payload.name,
                    payload.purpose,
                    payload.allocated_minor,
                    currency,
                    int(payload.protected),
                    pocket_id,
                    user["id"],
                ),
            )

    except sqlite3.IntegrityError:
        # Prevent duplicate pocket names.
        raise HTTPException(
            status_code=409,
            detail="A pocket with this name already exists",
        )

    return {
        "id": pocket_id,
        "name": payload.name,
        "purpose": payload.purpose,
        "allocated_minor": payload.allocated_minor,
        "spent_minor": pocket["spent_minor"],
        "available_minor": (
            payload.allocated_minor
            - pocket["spent_minor"]
        ),
        "currency": currency,
        "protected": payload.protected,
        "created_at": pocket["created_at"],
    }


# Delete a pocket owned by the authenticated user.
@app.delete("/v1/pockets/{pocket_id}", status_code=204)
def delete_pocket(
    pocket_id: str,
    user: dict = Depends(current_user),
) -> None:
    """Delete a pocket when it has not been used for spending."""

    # Load the pocket through the authenticated user's ID.
    with connection() as conn:
        pocket = conn.execute(
            """
            SELECT *
            FROM pockets
            WHERE id = ? AND user_id = ?
            """,
            (
                pocket_id,
                user["id"],
            ),
        ).fetchone()

    # Do not reveal another user's pocket.
    if not pocket:
        raise HTTPException(
            status_code=404,
            detail="Pocket not found",
        )

    # Prevent deletion after spending has occurred.
    if pocket["spent_minor"] > 0:
        raise HTTPException(
            status_code=409,
            detail="A pocket with spending history cannot be deleted",
        )

    try:
        # Delete only the authenticated user's pocket.
        with connection() as conn:
            conn.execute(
                """
                DELETE FROM pockets
                WHERE id = ? AND user_id = ?
                """,
                (
                    pocket_id,
                    user["id"],
                ),
            )

    except sqlite3.IntegrityError:
        # Keep referenced pockets safe.
        raise HTTPException(
            status_code=409,
            detail="This pocket cannot be deleted because it is already referenced",
        )


# Transfer allocated funds between two pockets owned by the authenticated user.
@app.post("/v1/pockets/transfer")
def transfer_pocket(
    payload: PocketTransferRequest,
    user: dict = Depends(current_user),
) -> dict:
    """Transfer allocated funds from one user-owned pocket to another."""

    # Prevent a meaningless transfer to the same pocket.
    if payload.source_pocket_id == payload.destination_pocket_id:
        raise HTTPException(
            status_code=422,
            detail="Source and destination pockets must be different",
        )

    # Load both pockets while enforcing ownership.
    with connection() as conn:
        source = conn.execute(
            """
            SELECT *
            FROM pockets
            WHERE id = ? AND user_id = ?
            """,
            (
                payload.source_pocket_id,
                user["id"],
            ),
        ).fetchone()

        destination = conn.execute(
            """
            SELECT *
            FROM pockets
            WHERE id = ? AND user_id = ?
            """,
            (
                payload.destination_pocket_id,
                user["id"],
            ),
        ).fetchone()

        # Reject missing or cross-user pockets.
        if source is None or destination is None:
            raise HTTPException(
                status_code=404,
                detail="Source or destination pocket not found",
            )

        # Transfers must remain within the same currency.
        if source["currency"] != destination["currency"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CURRENCY_MISMATCH",
                    "message": "Pocket transfers must use the same currency",
                },
            )

        # Calculate the source pocket's available amount.
        source_available_minor = (
            source["allocated_minor"]
            - source["spent_minor"]
        )

        # Prevent transferring more than the source can provide.
        if payload.amount_minor > source_available_minor:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INSUFFICIENT_POCKET_BALANCE",
                    "message": "Source pocket does not have enough available balance",
                    "available_minor": source_available_minor,
                    "requested_minor": payload.amount_minor,
                },
            )

        # Move allocation while preserving spending history.
        new_source_allocation = (
            source["allocated_minor"]
            - payload.amount_minor
        )

        new_destination_allocation = (
            destination["allocated_minor"]
            + payload.amount_minor
        )

        # Never allow allocation below money already spent.
        if new_source_allocation < source["spent_minor"]:
            raise HTTPException(
                status_code=422,
                detail="Transfer would reduce the source allocation below its spent amount",
            )

        # Apply both sides inside the same database transaction.
        conn.execute(
            """
            UPDATE pockets
            SET allocated_minor = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                new_source_allocation,
                source["id"],
                user["id"],
            ),
        )

        conn.execute(
            """
            UPDATE pockets
            SET allocated_minor = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                new_destination_allocation,
                destination["id"],
                user["id"],
            ),
        )

    return {
        "source": {
            "id": source["id"],
            "allocated_minor": new_source_allocation,
            "spent_minor": source["spent_minor"],
            "available_minor": (
                new_source_allocation
                - source["spent_minor"]
            ),
            "currency": source["currency"],
        },
        "destination": {
            "id": destination["id"],
            "allocated_minor": new_destination_allocation,
            "spent_minor": destination["spent_minor"],
            "available_minor": (
                new_destination_allocation
                - destination["spent_minor"]
            ),
            "currency": destination["currency"],
        },
        "amount_minor": payload.amount_minor,
    }


# Create a Currency Shield recommendation without immediately moving money.
@app.post("/v1/recommendations/currency-shield", status_code=201)
def create_currency_shield(
    payload: CurrencyShieldRequest,
    user: dict = Depends(current_user),
) -> dict:
    """Create a Currency Shield recommendation after safety checks."""

    # Load the pocket while enforcing ownership.
    with connection() as conn:
        pocket = row_dict(
            conn.execute(
                """
                SELECT *
                FROM pockets
                WHERE id = ? AND user_id = ?
                """,
                (
                    payload.pocket_id,
                    user["id"],
                ),
            ).fetchone()
        )

    if not pocket:
        raise HTTPException(
            status_code=404,
            detail="Pocket not found",
        )

    # Calculate the current available pocket balance.
    available = (
        pocket["allocated_minor"]
        - pocket["spent_minor"]
    )

    # Limit Currency Shield to the configured percentage of available funds.
    maximum = (
        available
        * settings.max_fx_conversion_percent
        // 100
    )

    reasons = []

   # Prevent protected pockets from funding Currency Shield.
    if pocket["protected"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PROTECTED_POCKET",
                "message": "Protected pockets cannot fund Currency Shield",
            },
        )

    # The current MVP supports only CNGN to USD.
    if (
        pocket["currency"] != "CNGN"
        or payload.target_currency.upper() != "USD"
    ):
        reasons.append("UNSUPPORTED_PAIR")

    # Enforce the Currency Shield safety limit.
    if payload.amount_minor > maximum:
        reasons.append("AMOUNT_EXCEEDS_SAFETY_LIMIT")

    # Only recommend conversion after the configured depreciation threshold is reached.
    if payload.observed_change_bps > -settings.fx_alert_threshold_bps:
        reasons.append("ALERT_THRESHOLD_NOT_REACHED")

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
        "observed_change_bps": payload.observed_change_bps,
        "observation_window_days": payload.observation_window_days,
        "max_conversion_percent": settings.max_fx_conversion_percent,
    }

    rationale = (
        f"CNGN changed "
        f"{abs(payload.observed_change_bps) / 100:.2f}% "
        f"over {payload.observation_window_days} days. "
        f"Consider diversifying part of this pocket."
    )

    disclosure = (
        "Rates can move in either direction. "
        "Conversion may include fees or spread. "
        "No money moves without approval."
    )

    # Store the recommendation without executing the conversion.
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO recommendations
            VALUES (
                ?,
                ?,
                ?,
                'CURRENCY_SHIELD',
                'AWAITING_APPROVAL',
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                NULL,
                ?
            )
            """,
            (
                recommendation_id,
                user["id"],
                pocket["id"],
                pocket["currency"],
                payload.target_currency.upper(),
                payload.amount_minor,
                rationale,
                disclosure,
                json_text(evidence),
                now_iso(),
            ),
        )

    return {
        "id": recommendation_id,
        "status": "AWAITING_APPROVAL",
        "rationale": rationale,
        "risk_disclosure": disclosure,
        "evidence": evidence,
        "requires_user_approval": True,
    }


# Approve and execute an existing Currency Shield recommendation.
@app.post("/v1/recommendations/{recommendation_id}/approve", status_code=201)
def approve_currency_shield(
    recommendation_id: str,
    idempotency_key: str = Header(
        min_length=8,
        max_length=128,
        alias="Idempotency-Key",
    ),
    user: dict = Depends(current_user),
) -> dict:
    """Approve a Currency Shield recommendation after revalidating its pocket."""

    with connection() as conn:
        # Return an existing conversion for repeated idempotency keys.
        existing = row_dict(
            conn.execute(
                """
                SELECT *
                FROM fx_conversions
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (
                    user["id"],
                    idempotency_key,
                ),
            ).fetchone()
        )

        if existing:
            return existing

        # Load the recommendation while enforcing ownership.
        recommendation = row_dict(
            conn.execute(
                """
                SELECT *
                FROM recommendations
                WHERE id = ? AND user_id = ?
                """,
                (
                    recommendation_id,
                    user["id"],
                ),
            ).fetchone()
        )

    if not recommendation:
        raise HTTPException(
            status_code=404,
            detail="Recommendation not found",
        )

    # Prevent already processed recommendations from being approved again.
    if recommendation["status"] != "AWAITING_APPROVAL":
        raise HTTPException(
            status_code=409,
            detail="Recommendation cannot be approved",
        )

    # Re-fetch the pocket to validate its current state at approval time.
    with connection() as conn:
        pocket = conn.execute(
            """
            SELECT *
            FROM pockets
            WHERE id = ? AND user_id = ?
            """,
            (
                recommendation["pocket_id"],
                user["id"],
            ),
        ).fetchone()

    # Reject approval if the pocket no longer exists or belongs to another user.
    if pocket is None:
        raise HTTPException(
            status_code=404,
            detail="Pocket not found",
        )

    # Prevent protected pockets from funding Currency Shield.
    if bool(pocket["protected"]):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PROTECTED_POCKET",
                "message": "Protected pockets cannot fund Currency Shield",
            },
        )

    # Calculate the pocket's currently available amount.
    available_minor = (
        pocket["allocated_minor"]
        - pocket["spent_minor"]
    )

    # Prevent approval when the pocket no longer has enough available funds.
    if recommendation["amount_minor"] > available_minor:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INSUFFICIENT_POCKET_BALANCE",
                "message": "Pocket does not have enough available balance",
                "available_minor": available_minor,
                "requested_minor": recommendation["amount_minor"],
            },
        )

    # Request the exchange quote using the authenticated BMONI user context.
    quote = bmoni.get_fx_quote(
        user_id=user["bmoni_user_id"],
        amount_minor=recommendation["amount_minor"],
        source=recommendation["source_currency"],
        target=recommendation["target_currency"],
    )

    # Execute the approved conversion for the authenticated BMONI user.
    remote = bmoni.execute_fx_conversion(
        user_id=user["bmoni_user_id"],
        quote_id=quote["id"],
        idempotency_key=idempotency_key,
    )

    # Record the source-currency amount spent from the pocket after successful conversion.
    with connection() as conn:
        conn.execute(
            """
            UPDATE pockets
            SET spent_minor = spent_minor + ?
            WHERE id = ? AND user_id = ?
            """,
            (
                recommendation["amount_minor"],
                recommendation["pocket_id"],
                user["id"],
            ),
        )

    conversion_id = new_id("fx")

    completed_at = (
        now_iso()
        if remote["status"] == "COMPLETED"
        else None
    )

    # Mark the recommendation executed and record the BMONI conversion.
    with connection() as conn:
        conn.execute(
            """
            UPDATE recommendations
            SET status = 'EXECUTED'
            WHERE id = ?
            """,
            (recommendation_id,),
        )

        conn.execute(
            """
            INSERT INTO fx_conversions
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversion_id,
                user["id"],
                recommendation_id,
                remote["id"],
                remote["status"],
                recommendation["amount_minor"],
                recommendation["source_currency"],
                recommendation["target_currency"],
                json_text(quote),
                idempotency_key,
                now_iso(),
                completed_at,
            ),
        )

    return {
        "id": conversion_id,
        "status": remote["status"],
        "quote": quote,
    }


# Expose verified investment opportunities without allowing investment execution.
@app.get(
    "/v1/investment-opportunities",
    response_model=list[InvestmentOpportunityResponse],
)
def list_investment_opportunities(
    user: dict = Depends(current_user),
) -> list[dict]:
    """Return verified investment opportunities as read-only information."""

    # Read the verified opportunities from the database.
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM investment_opportunities
            ORDER BY verified_at DESC
            """
        ).fetchall()

    # Return only informational investment fields.
    return [row_dict(row) for row in rows]
