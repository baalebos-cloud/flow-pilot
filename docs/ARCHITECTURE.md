# Architecture and controlled-action flow

```text
Flutter app ── FlowPilot JWT ──> FastAPI
    │                              ├── policy engine (deterministic)
    │                              ├── recommendation/audit store
    │                              ├── market-data adapter
    │                              └── BMONI gateway ──> BMONI API
    └── embedded BMONI SDK
        └── device key + signing PIN (never sent to backend)
```

## Trust boundaries

1. The LLM produces explanations and structured candidates only.
2. Deterministic code validates balances, pocket protection, currency pairs, thresholds, limits, quote expiry, and consent.
3. Only the BMONI gateway can call vendor financial endpoints.
4. State changes require authenticated ownership checks and idempotency.
5. The Flutter signing SDK owns private-key operations.

## Currency Shield state flow

```text
OBSERVED → NOT_RECOMMENDED | AWAITING_APPROVAL
AWAITING_APPROVAL → DECLINED | QUOTING
QUOTING → QUOTE_FAILED | QUOTE_READY
QUOTE_READY → EXPIRED | EXECUTING
EXECUTING → PROCESSING | COMPLETED | FAILED | REQUIRES_REVIEW
```

The current mock combines quote and execution for speed. Live integration must persist `QUOTE_READY`, show the real quote to the user, then require a second confirmation if the displayed values changed.

## Data ownership

- FlowPilot: app users, pockets, categorizations, recommendation evidence, consent, normalized transaction state.
- BMONI: embedded financial identity, wallets, KYC, balances, quotes, conversions, transfers, authoritative settlement status.
- Device: private key and signing PIN.

## Failure rules

- Never infer success from HTTP 200 alone; reconcile authoritative status.
- Unknown vendor states map to `REQUIRES_REVIEW`, not `COMPLETED`.
- Duplicate requests return the first result.
- Out-of-order webhooks cannot move a final transaction backward.
- A stale quote must be replaced and shown again before execution.

