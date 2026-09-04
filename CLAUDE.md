# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FlowPilot is an AI financial-optimization copilot built on top of BMONI (an embedded wallet/KYC provider). Users organize money into "pockets," get AI-generated recommendations (e.g. Currency Shield FX diversification), and approve controlled financial actions that a deterministic backend validates before ever touching BMONI.

Monorepo layout:
```
backend/   FastAPI service (Python) — auth, pockets, policy engine, BMONI gateway
frontend/  Flutter app (Dart) — screens, mock services, future API integration
docs/      Product/architecture/security/AI-contract docs — read these before big changes
```

Start with `docs/ARCHITECTURE.md` and `docs/AI_CONTRACT.md` for the trust-boundary model; it shapes how backend code must be written.

## Backend (`backend/`)

### Setup & run
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
Swagger UI: `http://127.0.0.1:8000/docs`

Docker (Postgres + Alembic migrations applied automatically):
```powershell
$env:FLOWPILOT_SECRET = "replace-with-a-long-random-secret"
docker compose up --build
```
Local (non-Docker) runs default to SQLite via `DATABASE_URL` in `.env`; Docker Compose uses PostgreSQL.

### Tests & lint
```powershell
cd backend
pytest                       # full suite
pytest tests/test_flow.py    # single file
pytest tests/test_flow.py::test_name   # single test
ruff check .
bandit -r app
pip-audit
```
No `pytest.ini`/`pyproject.toml` — pytest and ruff run with defaults from the CLI.

### Migrations
```powershell
alembic upgrade head
```
Models live in `app/models.py`; migrations in `backend/migrations/versions/`. Repositories (`app/repositories.py`) isolate route code from persistence — routes should not issue raw queries.

### Architecture: trust boundaries

This is the load-bearing concept in the backend. From `docs/ARCHITECTURE.md`:

1. The LLM (`app/ai/`) produces explanations and structured candidates only — it never calls BMONI or touches the database.
2. Deterministic code (in `app/main.py` route handlers) validates balances, pocket protection, currency pairs, thresholds, limits, quote expiry, and consent.
3. Only `app/bmoni.py` (the BMONI gateway) can call vendor financial endpoints.
4. State changes require authenticated ownership checks (`current_user` + user_id filtering in repository queries) and idempotency (`Idempotency-Key` header, checked before mutating state).
5. The Flutter app's embedded BMONI SDK owns private-key signing; the backend receives only public wallet addresses and signatures, never PINs or private keys.

The AI module boundary is enforced by `app/ai/contracts.py` (Pydantic models, all reject unknown fields) — this is the single source of truth for the backend↔AI interface described in `docs/AI_CONTRACT.md`. The AI engine only ever receives a `RecommendationRequest` and returns a `RecommendationOutcome`; it has no DB session, no BMONI client, no credentials. Money is always integer minor units; percentages/confidence are integer basis points.

### State machines

`app/workflow.py` defines allowed transitions for `ActionPlanStatus`, `RecommendationStatus`, and `TransactionStatus` (imported as `ACTION_PLAN_TRANSITIONS`, `RECOMMENDATION_TRANSITIONS`, `TRANSACTION_TRANSITIONS`). Every status write in `app/main.py` goes through `transition(current, target, table)` rather than assigning the field directly — this is what prevents e.g. a webhook from moving a completed transaction backward. When adding a new state or route that mutates status, extend the transition table rather than bypassing it.

Currency Shield states: `OBSERVED → NOT_RECOMMENDED | AWAITING_APPROVAL → DECLINED | QUOTING → QUOTE_FAILED | QUOTE_READY → EXPIRED | EXECUTING → PROCESSING | COMPLETED | FAILED | REQUIRES_REVIEW`. Unknown vendor states must map to `REQUIRES_REVIEW`, never `COMPLETED`. Webhook processing (`/v1/webhooks/bmoni`) is idempotent on event ID and verifies an HMAC signature (`BMONI_WEBHOOK_SECRET`) except when `FLOWPILOT_ENV=development`.

### BMONI integration

`app/bmoni.py` is the only file that should know about BMONI's real API. `BMONI_MODE=mock` (the default) provides a full deterministic demo path since the real BMONI schemas aren't confirmed yet. When real credentials arrive, only the five live-mode methods in `app/bmoni.py` need to change — the rest of the app talks to `bmoni` as an opaque gateway and must keep doing so.

### Financial routes convention

Approval/execution endpoints (`/v1/action-plans/{id}/approve`, `/v1/recommendations/{id}/approve`) share a pattern worth following for new ones: check idempotency key first → row-lock the record (`with_for_update()`) → transition to an intermediate "in flight" status → call the BMONI gateway outside the lock → on failure, transition to `FAILED` and re-raise → on success, re-fetch and transition to the final status, writing an audit row via `add_audit(...)`. Rate limiting (`enforce_rate_limit`) is applied per-user on every financial mutation.

## Frontend (`frontend/`)

### Setup & run
```bash
cd frontend
flutter pub get
flutter run
```
Requires Flutter 3.22+ / Dart 3.3+. `flutter create .` only if platform folders are missing — it preserves `lib/` and `pubspec.yaml`.

### Lint/analyze
```bash
flutter analyze
```
Rules: `flutter_lints` + `prefer_single_quotes`, `avoid_print` (see `analysis_options.yaml`).

### Tests
```bash
flutter test
flutter test test/some_test.dart
```

### Current state — read before touching routing or adding screens

The app is mid-migration between two different visions, and **the router only wires a subset of what's in `lib/features/`**:

- **Wired and live** (referenced by `lib/app/router.dart`): `features/auth`, `features/wallet`, `features/pockets`, `features/currency_shield`, plus `core/api_client.dart`, `core/secure_token_store.dart`, `core/health_*`. These integrate with the real FastAPI backend (`ApiClient` reads `API_BASE_URL` from `.env` via `core/environment.dart`).
- **Present but dormant** (not routed, not compiling standalone): `features/dashboard`, `features/activity`, `features/assistant`, `features/planning`, `features/approval`, `features/review`. These import `providers/`, `models/`, `services/`, `mock/` folders that do not exist in this repo — they're leftovers from an earlier all-mock hackathon-demo version of the app (wallet balances, transaction history, AI goal flow) that the current handoff scope explicitly excludes. Do not wire these into the router or assume their imports resolve without first checking whether the supporting layer exists; ask before deleting them, since they may be revived later.

When adding a screen, follow the pattern already established by `features/pockets` and `features/wallet`: a `*_repository.dart` that calls `ApiClient`, a model file, and a screen widget — no direct `Dio`/HTTP calls from widgets.

`ApiClient` (`lib/core/api_client.dart`) is the single owner of base URL, auth header injection (bearer token from `SecureTokenStore`), timeouts, and error mapping (401/403/409/422/503 → user-facing messages). Repositories call it; widgets never build raw requests.

`.env` sets `API_BASE_URL` — defaults to `10.0.2.2:8000` (Android emulator loopback to host) if unset. Change this per-target (physical device vs. emulator vs. iOS simulator) rather than hardcoding a URL anywhere else.

UI components come from the `bkey_uikit` package (`BMoniButton`, `BMoniTextFormField`, `BMoniTheme`, etc.) — check the package source under `~/.pub-cache` before assuming a constructor parameter exists; some usages in auth screens were written without confirming against the actual package API.

## Cross-cutting

- Amounts are always integer minor units end-to-end (backend schemas, AI contracts, and the frontend's `money_formatter.dart` all agree on this) — never introduce a float currency field.
- `docs/AI_CONTRACT.md` and `backend/app/ai/contracts.py` must stay in sync; the AI implementation imports the contracts module directly rather than duplicating types.
- Work is split by GitHub issue: platform/security/BMONI integration in issue #1, pockets/insights/fixtures/frontend-facing contracts in issue #2 (see root `README.md`).
