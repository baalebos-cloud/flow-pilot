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

## Intentionally blocked outside mock mode

- A bank withdrawal uses the Nigerian beneficiary/offramp sequence.
- A real stablecoin swap uses BMONI's signed proposal lifecycle. The
  `exchange/convert` endpoint is a preview calculation, not execution.

These operations must remain fail-closed until their request and response
models and mobile signing handoff are implemented from the confirmed schema.
