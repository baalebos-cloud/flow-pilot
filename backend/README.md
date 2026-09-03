# FlowPilot backend

Demo-ready FastAPI backend for smart pockets, Currency Shield, and FlowPilot's controlled financial-action pipeline.

## Shared documentation

- [Product requirements](../docs/PRD.md)
- [Architecture](../docs/ARCHITECTURE.md)
- [API contract](../docs/API.md)
- [Security baseline](../docs/SECURITY.md)
- [Tonight's runbook](../docs/TONIGHT_RUNBOOK.md)
- [Presentation pitch](../docs/PRESENTATION_PITCH.md)
- [Heavy backend issue](../docs/issues/01-platform-core.md)
- [Parallel backend issue](../docs/issues/02-pockets-recommendations.md)

## Locked hackathon assumptions

- Users register and log in with FlowPilot; they never enter a BMONI user ID.
- On first registration, the backend provisions a BMONI embedded user and stores the mapping.
- The Flutter app embeds BMONI's SDK. Wallet PIN checks and private-key signing happen on-device.
- The backend receives a public wallet address and transaction signatures, never the PIN/private key.
- `BMONI_MODE=mock` provides a full demo path until the real BMONI request schemas are confirmed.

## Run

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API.

Database migrations are managed with Alembic:

```powershell
alembic upgrade head
```

All runtime persistence uses SQLAlchemy. Local Python runs default to SQLite; Docker Compose uses PostgreSQL and applies Alembic migrations before starting the API.

## Docker (recommended)

From the repository root:

```powershell
$env:FLOWPILOT_SECRET = "replace-with-a-long-random-secret"
docker compose up --build
```

Stop the service without deleting the database volume:

```powershell
docker compose down
```

The backend container runs as UID/GID `10001`, drops Linux capabilities, and uses a read-only root filesystem. PostgreSQL owns the persistent named volume. Do not use either development password in a shared or deployed environment.

## Demo flow

1. `POST /v1/auth/register`
2. Copy `access_token` into Swagger's **Authorize** dialog.
3. `GET /v1/me` to see the FlowPilot-to-BMONI mapping.
4. `POST /v1/wallets/link` with the public address produced by the Flutter SDK.
5. `POST /v1/action-plans` to create a validated withdrawal recommendation.
6. `POST /v1/action-plans/{plan_id}/approve` with an `Idempotency-Key` header.
7. `GET /v1/transactions/{transaction_id}/signing-payload`.
8. Flutter signs `hash` locally with `BmoniEmbeddedSdk.signTransactionHash(...)`.
9. `POST /v1/transactions/{transaction_id}/signature`.
10. `GET /v1/transactions/{transaction_id}` shows the confirmed mock result.

Example action plan:

```json
{
  "message": "Move 100000 naira to my bank so it is safely set aside",
  "amount_minor": 10000000,
  "currency": "CNGN",
  "recipient_name": "Demo Bank •••• 4821",
  "available_balance_minor": 30000000
}
```

Amounts use minor units: `10000000` means NGN 100,000.00.

## Connecting the real BMONI API

All unconfirmed vendor behavior lives in `app/bmoni.py`. Replace the five live-mode methods there once BMONI provides the exact URL, authentication headers, and payloads. The rest of the application does not need to change.
