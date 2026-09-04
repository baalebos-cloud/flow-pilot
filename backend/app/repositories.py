from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ActionPlan,
    AuditEvent,
    FxConversion,
    Pocket,
    Recommendation,
    Transaction,
    User,
    Wallet,
    WebhookEvent,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_user_by_id(session: Session, user_id: str) -> User | None:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


def get_wallet_by_user(session: Session, user_id: str) -> Wallet | None:
    return session.scalar(select(Wallet).where(Wallet.user_id == user_id))


def get_action_plan(session: Session, plan_id: str, user_id: str) -> ActionPlan | None:
    return session.scalar(
        select(ActionPlan).where(ActionPlan.id == plan_id, ActionPlan.user_id == user_id)
    )


def get_transaction(session: Session, transaction_id: str, user_id: str) -> Transaction | None:
    return session.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.user_id == user_id
        )
    )


def get_transaction_by_idempotency(
    session: Session, user_id: str, key: str
) -> Transaction | None:
    return session.scalar(
        select(Transaction).where(
            Transaction.user_id == user_id, Transaction.idempotency_key == key
        )
    )


def get_pocket(session: Session, pocket_id: str, user_id: str) -> Pocket | None:
    return session.scalar(
        select(Pocket).where(Pocket.id == pocket_id, Pocket.user_id == user_id)
    )


def list_user_pockets(session: Session, user_id: str) -> list[Pocket]:
    return list(
        session.scalars(
            select(Pocket).where(Pocket.user_id == user_id).order_by(Pocket.created_at)
        )
    )


def get_recommendation(
    session: Session, recommendation_id: str, user_id: str
) -> Recommendation | None:
    return session.scalar(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.user_id == user_id,
        )
    )


def get_fx_by_idempotency(session: Session, user_id: str, key: str) -> FxConversion | None:
    return session.scalar(
        select(FxConversion).where(
            FxConversion.user_id == user_id, FxConversion.idempotency_key == key
        )
    )


def get_webhook_event(session: Session, event_id: str) -> WebhookEvent | None:
    return session.get(WebhookEvent, event_id)


def get_transaction_by_proposal(session: Session, proposal_id: str) -> Transaction | None:
    return session.scalar(
        select(Transaction).where(Transaction.bmoni_proposal_id == proposal_id)
    )


def add_audit(
    session: Session,
    *,
    event_id: str,
    actor_user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str,
    metadata_json: str = "{}",
) -> None:
    session.add(
        AuditEvent(
            id=event_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            metadata_json=metadata_json,
            created_at=utc_now(),
        )
    )

