"""Authoritative backend-to-AI boundary for FlowPilot."""

from app.ai.contracts import RecommendationOutcome, RecommendationRequest
from app.ai.interface import RecommendationEngine

__all__ = ["RecommendationEngine", "RecommendationOutcome", "RecommendationRequest"]

