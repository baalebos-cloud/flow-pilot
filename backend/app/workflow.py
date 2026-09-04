from enum import StrEnum


class InvalidStateTransition(ValueError):
    pass


class ActionPlanStatus(StrEnum):
    AWAITING_USER_APPROVAL = "AWAITING_USER_APPROVAL"
    CREATING_PROPOSAL = "CREATING_PROPOSAL"
    APPROVED = "APPROVED"
    FAILED = "FAILED"


class TransactionStatus(StrEnum):
    PENDING_SIGNATURE = "PENDING_SIGNATURE"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class RecommendationStatus(StrEnum):
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


ACTION_PLAN_TRANSITIONS = {
    ActionPlanStatus.AWAITING_USER_APPROVAL: {ActionPlanStatus.CREATING_PROPOSAL},
    ActionPlanStatus.CREATING_PROPOSAL: {
        ActionPlanStatus.APPROVED,
        ActionPlanStatus.FAILED,
    },
    ActionPlanStatus.APPROVED: set(),
    ActionPlanStatus.FAILED: set(),
}

TRANSACTION_TRANSITIONS = {
    TransactionStatus.PENDING_SIGNATURE: {
        TransactionStatus.PROCESSING,
        TransactionStatus.COMPLETED,
        TransactionStatus.FAILED,
        TransactionStatus.REQUIRES_REVIEW,
    },
    TransactionStatus.PROCESSING: {
        TransactionStatus.COMPLETED,
        TransactionStatus.FAILED,
        TransactionStatus.REQUIRES_REVIEW,
    },
    TransactionStatus.COMPLETED: set(),
    TransactionStatus.FAILED: set(),
    TransactionStatus.REQUIRES_REVIEW: {
        TransactionStatus.PROCESSING,
        TransactionStatus.COMPLETED,
        TransactionStatus.FAILED,
    },
}

RECOMMENDATION_TRANSITIONS = {
    RecommendationStatus.AWAITING_APPROVAL: {RecommendationStatus.EXECUTING},
    RecommendationStatus.EXECUTING: {
        RecommendationStatus.EXECUTED,
        RecommendationStatus.FAILED,
    },
    RecommendationStatus.EXECUTED: set(),
    RecommendationStatus.FAILED: set(),
}


def transition(current: str, target: StrEnum, allowed: dict[StrEnum, set[StrEnum]]) -> str:
    try:
        current_state = type(target)(current)
    except ValueError as exc:
        raise InvalidStateTransition(f"Unknown current state: {current}") from exc
    if target not in allowed[current_state]:
        raise InvalidStateTransition(f"Cannot transition from {current_state} to {target}")
    return target.value
