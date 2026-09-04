"""Create secure platform core tables.

Revision ID: 20260903_0001
Revises:
"""
from typing import Sequence

from alembic import op


revision: str = "20260903_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Models remain the single schema authority; this initial migration is generated
    # from the reviewed metadata rather than the legacy sqlite bootstrap.
    from app.models import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.models import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
