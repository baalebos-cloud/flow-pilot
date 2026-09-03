# Backend task B — pockets, insights, and frontend contract

**Recommended owner: second backend developer**

## Scope

- Work primarily under `backend/`; coordinate before editing shared files in `docs/`.
- Implement pocket CRUD, allocation validation, transfers, and transaction categorization.
- Prevent aggregate allocation above authoritative wallet balance.
- Implement protected-pocket behavior and pocket summaries.
- Create read-only verified investment-opportunity model/fixtures; no execution.
- Publish OpenAPI examples and seed the agreed demo scenario.
- Add unit/API tests for pocket and recommendation edge cases.

## Acceptance criteria

- Demo user can create the agreed pockets and see allocated/spent/available totals.
- Protected pockets cannot fund Currency Shield.
- Invalid allocations and cross-user access are rejected.
- Investment records expose provider/regulatory/risk/liquidity/fee fields and cannot execute.
- Tests cover insufficient balance, unsupported currency, duplicate names, and ownership.
