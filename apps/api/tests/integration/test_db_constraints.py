"""Database-level guarantees: share-sum trigger, composite tenant FKs, append-only history."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.conftest import FrozenClock, TestUser
from tests.integration.helpers import add_expense, make_house


@pytest.fixture
def expense(
    client: TestClient, make_user: Callable[[str], TestUser], frozen_clock: FrozenClock
) -> tuple[str, str, str]:
    frozen_clock.set(datetime(2026, 3, 5, tzinfo=UTC))
    house = make_house(client, make_user, ("Juli", "Franco"))
    e = add_expense(client, house, "Juli", amount=1000, payer="Juli", date="2026-03-03")
    other = make_house(client, make_user, ("Bea", "Carlos"))
    return e["id"], house.id, other.members["Bea"]


def test_share_sum_trigger(db_session: Session, expense: tuple[str, str, str]) -> None:
    eid, _, _ = expense
    sp = db_session.begin_nested()
    db_session.execute(
        text("UPDATE app.expense_shares SET amount_cents = amount_cents + 1 WHERE expense_id = :e"),
        {"e": eid},
    )
    with pytest.raises(DBAPIError, match="shares sum"):
        db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    sp.rollback()


def test_amount_change_without_shares_fails(
    db_session: Session, expense: tuple[str, str, str]
) -> None:
    eid, _, _ = expense
    sp = db_session.begin_nested()
    db_session.execute(
        text("UPDATE app.expenses SET amount_cents = 5000 WHERE id = :e"), {"e": eid}
    )
    with pytest.raises(DBAPIError, match="shares sum"):
        db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    sp.rollback()


def test_cross_tenant_member_rejected(db_session: Session, expense: tuple[str, str, str]) -> None:
    eid, _, foreign_member = expense
    sp = db_session.begin_nested()
    with pytest.raises(DBAPIError, match="foreign key"):
        db_session.execute(
            text("UPDATE app.expenses SET payer_member_id = :m WHERE id = :e"),
            {"m": foreign_member, "e": eid},
        )
    sp.rollback()


def test_revisions_append_only(db_session: Session, expense: tuple[str, str, str]) -> None:
    eid, _, _ = expense
    sp = db_session.begin_nested()
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(
            text("UPDATE app.expense_revisions SET reason = 'x' WHERE expense_id = :e"), {"e": eid}
        )
    sp.rollback()


def test_rls_enabled_everywhere(db_session: Session) -> None:
    missing = (
        db_session.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'app' "
                "AND tablename <> 'alembic_version' AND NOT rowsecurity"
            )
        )
        .scalars()
        .all()
    )
    assert missing == []
