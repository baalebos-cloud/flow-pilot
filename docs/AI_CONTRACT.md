# Backend ↔ AI contract v1.0

The authoritative Pydantic models live in `backend/app/ai/contracts.py`. Member 3 must import those models directly and must not maintain a second copy.

The authenticated HTTP entry point is `POST /v1/ai/recommend`. Backend-owned
context is assembled inside the service; clients submit only the natural-language
message. Recommendation types without authoritative references are not enabled.

Natural-language currency values are major units. For example, "50,000 naira"
is normalized to `5_000_000` CNGN minor units before policy validation.

## Boundary

```text
Backend builds sanitized request
→ RecommendationEngine.recommend(request)
→ typed outcome
→ backend reference and policy validation
→ user-facing recommendation or clarification
```

The AI module cannot access BMONI credentials, financial execution clients, private keys, PINs, raw KYC documents, or the database.

## Outcomes

- `RECOMMENDATION`: typed candidate requiring backend validation.
- `CLARIFICATION_REQUIRED`: one bounded question for missing context.
- `UNSUPPORTED`: request is outside the allowed product surface.
- `MODEL_ERROR`: fail-closed timeout, invalid output, provider outage, or internal failure.

## Security rules

- All models reject unknown fields.
- All references must be selected from the backend request.
- Market and opportunity facts must be backend-supplied evidence.
- Money is represented as integer minor units.
- Percentages/confidence use integer basis points.
- The backend derives approval from action type; the AI value is never authoritative.
- Protected pockets cannot fund Currency Shield.
- Model metadata and prompt version accompany auditable outcomes.

## Member 3 implementation

```python
from app.ai.contracts import RecommendationOutcome, RecommendationRequest


class Member3Engine:
    async def recommend(
        self, request: RecommendationRequest
    ) -> RecommendationOutcome:
        # Call the selected provider and validate its structured output.
        ...
```

The engine receives a maximum of eight seconds through `RecommendationService` by default. It returns only a typed outcome and performs no financial action.

