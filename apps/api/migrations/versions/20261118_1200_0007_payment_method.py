"""Payment method: how the money moved (Bizum, bank transfer, cash, other).

The API requires it on every new payment. The column stays nullable so payments
recorded before this revision keep no method instead of a guessed one.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-18 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of models.payments.PAYMENT_METHODS at this revision.
METHODS = ("bizum", "bank_transfer", "cash", "other")


def upgrade() -> None:
    op.add_column("payments", sa.Column("method", sa.String(16), nullable=True), schema="app")
    quoted = ", ".join(f"'{m}'" for m in METHODS)
    op.create_check_constraint(
        op.f("ck_payments_method"), "payments", f"method IN ({quoted})", schema="app"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_payments_method"), "payments", type_="check", schema="app")
    op.drop_column("payments", "method", schema="app")
