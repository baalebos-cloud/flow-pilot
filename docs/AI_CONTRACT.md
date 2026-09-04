# FlowPilot AI Contract v1.0

## Purpose

The AI module is a recommendation engine only.

The security boundary is:

```text
User message
    ↓
Backend builds sanitized RecommendationRequest
    ↓
RecommendationEngine.recommend(request)
    ↓
Typed recommendation outcome
    ↓
Deterministic backend reference and policy validation
    ↓
User-facing recommendation or clarification
    ↓
Explicit user approval
    ↓
BMONI execution/signing