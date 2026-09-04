import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.ai.contracts import (
    ModelFailure,
    PocketContext,
    PocketPurpose,
    RecommendationContext,
    RecommendationOutcome,
    RecommendationRequest,
    RecommendationType,
)
from app.ai.engine import Member3Engine
from app.ai.policy import ValidatedRecommendation
from app.ai.service import RecommendationService
from app.database import session_scope
from app.models import User
from app.repositories import list_user_pockets


class AIRecommendationRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


def build_ai_router(
    current_user_dependency: Callable,
    engine_factory: Callable[[], Member3Engine] = Member3Engine,
) -> APIRouter:
    router = APIRouter(prefix="/v1/ai", tags=["AI recommendations"])

    @router.post("/recommend")
    async def recommend(
        payload: AIRecommendationRequest,
        user: User = Depends(current_user_dependency),
    ) -> dict:
        with session_scope() as session:
            stored_pockets = list_user_pockets(session, user.id)
            pockets = [
                PocketContext(
                    reference_id=pocket.id,
                    purpose=_pocket_purpose(pocket.purpose),
                    currency=pocket.currency,
                    available_minor=max(
                        0, pocket.allocated_minor - pocket.spent_minor
                    ),
                    protected=pocket.protected,
                )
                for pocket in stored_pockets
            ]
        request = RecommendationRequest(
            request_id=f"ai_{uuid.uuid4().hex}",
            user_message=payload.message,
            context=RecommendationContext(
                base_currency="CNGN",
                pockets=pockets,
                allowed_recommendation_types={
                    RecommendationType.POCKET_CREATION,
                    RecommendationType.SPENDING_ANALYSIS,
                },
            ),
        )
        try:
            engine = engine_factory()
        except RuntimeError:
            return _provider_unavailable(request).root.model_dump(mode="json")
        result = await RecommendationService(engine).recommend(request)
        if isinstance(result, ValidatedRecommendation):
            body = result.recommendation.model_dump(mode="json")
            body["requires_user_approval"] = result.requires_user_approval
            return body
        return result.root.model_dump(mode="json")

    return router


def _pocket_purpose(value: str) -> PocketPurpose:
    normalized = value.strip().upper()
    try:
        return PocketPurpose(normalized)
    except ValueError:
        return PocketPurpose.OTHER


def _provider_unavailable(request: RecommendationRequest) -> RecommendationOutcome:
    return RecommendationOutcome(
        ModelFailure(
            outcome="MODEL_ERROR",
            request_id=request.request_id,
            error_code="PROVIDER_UNAVAILABLE",
            retryable=False,
        )
    )
