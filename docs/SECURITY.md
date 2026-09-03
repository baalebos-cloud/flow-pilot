# Security and trust baseline

## Non-negotiable invariants

- The backend and AI never receive wallet PINs or private keys.
- The LLM cannot call financial APIs.
- No money moves without explicit, recorded user approval.
- Protected pockets are excluded from recommendations.
- BMONI remains the authority for balances and settlement.

## Controls in this scaffold

- Argon2id password hashing via `argon2-cffi`.
- Short-lived signed access tokens.
- Pydantic request validation and ownership-scoped database queries.
- Integer money representation.
- Idempotency constraints for money-moving operations.
- Constant-time HMAC webhook comparison and replay-event storage.
- Timestamp-bound webhook signatures with a configurable maximum request age.
- Explicit allowlisted state transitions for approvals, transactions, and recommendations.
- Application-layer throttling for authentication and money-moving endpoints.
- Environment-only secrets and committed `.env.example`.
- Pinned production/development dependencies.
- `bandit`, `pip-audit`, and `ruff` security/quality gates.
- BMONI live mode fails closed until confirmed schemas are implemented.
- Container runs as a fixed non-root UID with dropped capabilities and `no-new-privileges`.
- Container root filesystem is read-only; only the explicit database volume and limited `/tmp` are writable.
- The runtime image installs production dependencies only.

## Required before production

- Use a managed identity provider with MFA/OTP and refresh-token rotation.
- Replace SQLite with encrypted managed PostgreSQL and migrations.
- Add distributed API-gateway rate limits, WAF, TLS, CORS allowlist, and secure headers.
- Store BMONI secrets in a cloud secret manager with rotation.
- Encrypt sensitive PII fields and define retention/deletion policies.
- Verify wallet ownership using a server nonce and recovered signature.
- Use BMONI's confirmed webhook scheme; the current HMAC shape is a placeholder.
- Add immutable audit logs, monitoring, alerts, backups, and incident runbooks.
- Commission threat modelling, penetration testing, and regulatory/legal review.

## CI commands

```powershell
cd backend
ruff check app tests
bandit -r app
pip-audit -r requirements.txt
pytest -q
```

Passing these checks reduces common risks; it does not constitute a security certification.

## Container checks

```powershell
docker compose config
docker compose build --pull
docker compose up -d
docker compose ps
docker compose exec backend id
```

Expected runtime identity is UID/GID `10001`. Add a container-image vulnerability scan in CI before deployment; image scanning complements, but does not replace, the Python dependency audit.
