# BMONI sandbox integration

Source of truth: [BMONI Embedded API](https://bkey.mintlify.app/api) and the
sandbox OpenAPI document at `https://embedded-dev.bmoni.com/docs/openapi.json`.

## Configuration

- `BMONI_MODE=mock` keeps all external calls deterministic for local tests.
- `BMONI_MODE=sandbox` enables implemented sandbox operations.
- `BMONI_BASE_URL=https://embedded-dev.bmoni.com` contains no trailing `/v1`.
- `BMONI_API_KEY` is sent as `x-api-key` and must never be committed or logged.

## Implemented sandbox operation

`POST /v1/users` provisions the BMONI user using FlowPilot's stable local user
ID as `identityId`. The required FlowPilot fields include `first_name`,
`last_name`, `email`, and an E.164 `phone_number`; they map directly to the
BMONI identity fields. FlowPilot persists the returned `bmoniUserId`.

BMONI does not currently accept idempotency keys. If user creation returns
`409`, FlowPilot reads the partner user list and recovers the matching
`identityId` or email rather than blindly creating again.

## Managed-wallet handshake

1. The frontend generates or loads the EVM owner wallet using BMONI's mobile SDK.
2. It sends only the owner address and `CNGN` to
   `POST /v1/wallets/owner-proof-challenges`.
3. The backend returns BMONI's exact EIP-191 message and challenge metadata.
4. The SDK unlocks locally with the user's PIN and signs the exact message.
5. The frontend submits the signature and challenge ID to
   `POST /v1/wallets/managed`.
6. FlowPilot asks BMONI to create the managed wallet and stores only public
   wallet metadata. The PIN and private key never reach the backend.

Before creating, FlowPilot lists the user's BMONI wallets and reuses an
existing wallet for the requested currency. It repeats that read after an
ambiguous retryable failure, preventing blind duplicate wallet creation.

## Authoritative balances

`GET /v1/wallets/balances` reads BMONI's account-level balances and converts
decimal strings to integer minor units using `Decimal`, never binary floating
point. BMONI's `NGN` balance label is normalized to FlowPilot's `CNGN`.

The sandbox currently returns `smartAccountAddress` and `balances` at the
response top level, while earlier examples used a `data` envelope. The BMONI
gateway accepts either vendor shape and normalizes it to one internal envelope
before balance policy runs. Missing or malformed balance arrays fail closed.

An upstream per-currency read failure is represented as unavailable, not as a
zero balance. Internal allocation policies can call `available_balance_minor`
and fail closed when the authoritative balance cannot be read.

## Currency Shield quote

`POST /v1/fx/quotes` checks the requested CNGN amount against the authoritative
BMONI balance before requesting an `exactIn` NGN-to-USD quote. The response
includes the quote ID, rate, output, fees, and expiry and explicitly states
that no money has moved. Quote retrieval never authorizes execution.

FlowPilot validates the vendor currencies and exact input amount, requires
positive finite decimal amounts/rates, validates every fee, and rejects missing
or expired quote timestamps before the quote can be used to create a proposal.
On 4 September 2026, the shared sandbox credentials and the live NGN 1,000 to
USD quote response were verified without creating a proposal or moving funds.

The proposal approval route is omitted from the current sandbox OpenAPI
document but is active at
`POST /v1/users/{userId}/smart-wallets/proposals/{proposalId}/approve`.
On 4 September 2026, a request using a deliberately nonexistent proposal ID
reached the handler and returned BMONI `E501` / `Proposal not found`. FlowPilot
now treats the guide and verified runtime behavior as authoritative for this
route. Successful execution still requires a funded wallet and a real proposal.

## Current execution boundary

- A bank withdrawal uses the Nigerian beneficiary/offramp sequence.
- A real stablecoin swap uses BMONI's signed proposal lifecycle; the backend
  implements proposal creation, approval, signing-payload retrieval, signature
  submission, and status reconciliation. The mobile SDK must produce the owner
  proof and proposal signature, and the sandbox wallet must be funded.
- The `exchange/convert` endpoint is a preview calculation, not execution and
  is not used as proof that money moved.

Bank withdrawals remain fail-closed outside mock mode until the beneficiary and
offramp request/response models are confirmed. A real swap demo remains blocked
until the team supplies a funded SDK-controlled sandbox wallet; shared sandbox
wallets sampled on 4 September 2026 had no positive balance.
