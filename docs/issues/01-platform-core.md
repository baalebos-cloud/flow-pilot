# Backend task A — secure platform core and BMONI integration (heavy)

**Recommended owner: Favour**

## Scope

- Work only under `backend/` except when updating shared contracts in `docs/`.
- Finalize auth/session architecture and PostgreSQL migrations.
- Confirm and implement BMONI embedded-user onboarding/linking.
- Implement wallet ownership proof, balance/KYC sync, and webhook verification.
- Replace mock FX quote/execution methods in `backend/app/bmoni.py` using confirmed BMONI contracts.
- Implement state machine, idempotency, reconciliation, error mapping, audit events, and rate limiting.
- Add integration/contract/security tests and CI gates.
- Maintain the hardened backend Docker image, Compose service, health checks, and image scanning.
- Document all vendor discoveries and update API examples.

## Acceptance criteria

- One sandbox user completes onboarding and a real CNGN→USD quote/conversion end to end.
- No PIN/private key enters backend logs, payloads, or storage.
- Duplicate approvals cannot execute twice.
- Invalid/stale quotes and forged/replayed webhooks fail closed.
- From `backend/`, `pytest`, `ruff`, `bandit`, and `pip-audit` pass.
