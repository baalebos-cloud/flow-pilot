# API contract (scaffold)

The internal backend-to-AI API is documented separately in `docs/AI_CONTRACT.md`.

Interactive documentation is available at `/docs` while the service runs.

## Implemented endpoints

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Health and integration mode |
| POST | `/v1/auth/register` | FlowPilot registration plus mock BMONI provisioning |
| POST | `/v1/auth/login` | FlowPilot access token |
| GET | `/v1/me` | Current identity mapping |
| POST | `/v1/wallets/link` | Link public SDK wallet address |
| POST/GET | `/v1/pockets` | Create/list virtual pockets |
| POST | `/v1/recommendations/currency-shield` | Deterministic eligibility and explanation |
| POST | `/v1/recommendations/{id}/approve` | Quote and execute approved mock conversion |
| POST | `/v1/action-plans` | Legacy withdrawal plan retained for reference demo |
| POST | `/v1/action-plans/{id}/approve` | Create mock withdrawal proposal |
| GET | `/v1/transactions/{id}/signing-payload` | Payload for on-device signing |
| POST | `/v1/transactions/{id}/signature` | Submit signature, never PIN/key |
| POST | `/v1/webhooks/bmoni` | Signed asynchronous events |

## Contract conventions

- All money fields end in `_minor` and are integers.
- State-changing retryable calls require `Idempotency-Key`.
- Vendor payloads do not leak through the public API.
- Error responses use stable codes before frontend integration begins.
- `BMONI_MODE=mock` responses are synthetic and must be labelled in the demo UI.
