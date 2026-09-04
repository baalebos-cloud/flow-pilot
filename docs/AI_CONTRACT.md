
# FlowPilot AI Contract

## Purpose

The AI module is a recommendation engine only.

The security boundary is:

AI interprets user intent
→ deterministic backend validates policy
→ user approves
→ BMONI executes and signs

The AI must never execute financial actions, access private keys, handle PINs,
or bypass backend approval and policy controls.

## Request flow

The backend creates a sanitized `RecommendationRequest`.

The request contains:

- user message
- base currency
- available pockets
- saved recipients
- market observations
- verified investment opportunities
- allowed recommendation types

The AI must use only the references supplied by the backend.

## Engine interface

Member 3 implements:

```python
from app.ai.contracts import RecommendationOutcome, RecommendationRequest

class Member3Engine:
    async def recommend(
        self,
        request: RecommendationRequest,
    ) -> RecommendationOutcome:
        ...