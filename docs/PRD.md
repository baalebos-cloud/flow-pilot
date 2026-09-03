# FlowPilot Product Requirements Document

## Product statement

FlowPilot is an AI financial-optimization copilot for BMONI users. It organizes balances into smart pockets, detects spending and currency risks, explains suitable actions, and executes only actions the user explicitly approves through BMONI.

## Commercial thesis

The product should increase BMONI wallet retention, transaction frequency, and FX conversion volume. Future regulated-partner referrals and a premium planning tier provide additional revenue paths.

## MVP story

A user with a CNGN balance creates purpose-based pockets. FlowPilot identifies surplus in an unprotected savings pocket after a defined adverse currency movement, explains a limited CNGN-to-USD conversion—including rate, fees, risks, and resulting balances—and executes it only after approval.

## Personas

- A Nigerian wallet user paid or saving in NGN who wants visibility and discipline.
- A user concerned about currency exposure but not confident enough to trade manually.
- A user interested in legitimate investments but needing plain-language education.

## Functional requirements

### Accounts and wallets

- FlowPilot owns application authentication.
- The backend maps each FlowPilot user to the BMONI embedded-user identifier returned by the confirmed onboarding API.
- The Flutter SDK provisions/signs on-device; FlowPilot never receives a PIN or private key.
- KYC state is displayed and blocks regulated actions when incomplete.

### Smart pockets

- Create, rename, archive, and fund virtual purpose pockets.
- Prevent total allocations from exceeding the actual wallet balance.
- Mark essential pockets (rent/emergency) as protected.
- Categorize transactions and show allocated, spent, and available amounts.
- Clearly label pockets as virtual allocations unless BMONI confirms real sub-wallet support.

### Currency Shield

- Consume a traceable market-rate source and record timestamp/source.
- Evaluate deterministic thresholds; the AI may explain but may not decide eligibility.
- Never recommend funds from protected pockets.
- Cap suggested conversion size and re-check balance immediately before execution.
- Display rate, spread/fees, expiry, converted amount, remaining balance, and downside warning.
- Require explicit approval and an idempotency key.

### Investment discovery (stretch)

- List only opportunities supplied by verified, regulated partners.
- Present factual attributes: provider, regulator status, risk, liquidity, fees, term, and historical/expected return wording approved by compliance.
- No autonomous investing, guaranteed returns, portfolio management, or execution in the MVP.

## Non-functional requirements

- Money uses integer minor units; FX rates use fixed precision.
- All state-changing calls are authenticated, authorized, validated, logged, and idempotent.
- Secrets stay server-side and out of source control/logs.
- Webhooks require signature verification and replay protection.
- Recommendation evidence and user approval are auditable.
- The demo must work in explicit mock mode without presenting simulation as a live transaction.

## Success metrics

- Pocket activation rate and allocation completion.
- Percentage of recommendations opened and approved.
- Incremental BMONI FX volume and retained wallet balance.
- Recommendation rejection/cancellation rate.
- Zero duplicate executions and zero actions without recorded consent.

## Explicit exclusions

- Autonomous currency conversion or investment.
- Scraping unverified opportunities.
- Claims that pockets hold separate funds without supporting rails.
- The LLM directly calling BMONI.
- Custody of user keys or PINs.

## Open vendor decisions

1. Exact BMONI base/proxy URL, auth headers, token lifecycle, and user creation schema.
2. Existing-user linking/deduplication behavior.
3. Wallet-to-user ownership proof and KYC endpoints.
4. FX quote/execution schemas, fees, supported pairs, settlement states, and limits.
5. Webhook signing algorithm, event IDs, retries, and ordering guarantees.
6. Whether BMONI provides sub-wallets, metadata, or transaction categorization.

