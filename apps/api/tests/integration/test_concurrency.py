"""Real concurrency between transactions (committed data, several connections).

Unlike the other integration tests these do not run inside the rolled-back test
transaction: each case commits its own group and truncates the `app` tables afterwards.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from split_ranch.core.actor import GroupActor
from split_ranch.core.errors import AppError
from split_ranch.core.security import TokenVerifier
from split_ranch.core.settings import Settings
from split_ranch.main import create_app
from split_ranch.schemas.expenses import ExpenseCreate
from split_ranch.schemas.groups import CategoryCreate, CategoryPresetCreate, CategoryUpdate
from split_ranch.schemas.payments import PaymentCreate
from split_ranch.use_cases.expenses import create_expense
from split_ranch.use_cases.payments import record_payment
from split_ranch.use_cases.rules import create_category, create_category_preset, update_category
from tests.conftest import TestUser
from tests.integration.helpers import House, make_house

# Long enough for the writer to reach the lock, short enough to keep the test fast.
BLOCK_CHECK_SECONDS = 0.5
FINISH_TIMEOUT_SECONDS = 10


def _truncate_app_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                "SELECT quote_ident(tablename) FROM pg_tables "
                "WHERE schemaname = 'app' AND tablename <> 'alembic_version'"
            )
        ).scalars()
        names = ", ".join(f"app.{t}" for t in tables)
        # TRUNCATE skips the row-level append-only trigger on history.
        conn.execute(text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture
def committed_client(
    settings: Settings, engine: Engine, token_verifier: TokenVerifier
) -> Iterator[TestClient]:
    """A client whose requests commit for real (no rolled-back session override)."""
    application = create_app(settings, engine=engine, token_verifier=token_verifier)
    try:
        with TestClient(application, raise_server_exceptions=True) as c:
            yield c
    finally:
        _truncate_app_tables(engine)


def _juli(house: House) -> GroupActor:
    return GroupActor(
        user_id=house.users["Juli"].id,
        group_id=uuid.UUID(house.id),
        member_id=uuid.UUID(house.members["Juli"]),
        role="admin",
        status="active",
    )


def _write_with_ana(kind: str, house: House) -> Callable[[Session], object]:
    """An expense paid by Ana, or a payment to Ana, recorded by Juli."""
    ana = uuid.UUID(house.members["Ana"])
    if kind == "expense":
        data = ExpenseCreate(
            amount_cents=3000,
            description="Cena",
            payer_member_id=ana,
            expense_date=date(2026, 11, 27),
        )
        return lambda s: create_expense(s, _juli(house), data)
    payment = PaymentCreate(
        id=uuid.uuid4(),
        from_member_id=uuid.UUID(house.members["Juli"]),
        to_member_id=ana,
        amount_cents=1000,
        method="bizum",
    )
    return lambda s: record_payment(s, _juli(house), payment)


@pytest.mark.parametrize(("kind", "code"), [("expense", "invalid_payer"), ("payment", None)])
def test_write_waits_for_leave_and_sees_the_member_gone(
    committed_client: TestClient,
    make_user: Callable[[str], TestUser],
    engine: Engine,
    kind: str,
    code: str | None,
) -> None:
    """C1: a write racing a departure must not leave the departed member with a balance.

    The departure holds the group FOR UPDATE (as `leave_group` does) while it settles the
    member; the write has to wait for it and then reject the member who left.
    """
    house = make_house(committed_client, make_user)
    write = _write_with_ana(kind, house)
    outcome: dict[str, object] = {}

    def run() -> None:
        with Session(engine, expire_on_commit=False) as session:
            try:
                outcome["result"] = write(session)
            except AppError as exc:
                outcome["error"] = exc

    with engine.connect() as leaving:
        tx = leaving.begin()
        try:
            leaving.execute(
                text("SELECT id FROM app.groups WHERE id = :g FOR UPDATE"), {"g": house.id}
            )
            leaving.execute(
                text("UPDATE app.group_members SET status = 'left', left_at = now() WHERE id = :m"),
                {"m": house.members["Ana"]},
            )
            writer = threading.Thread(target=run)
            writer.start()
            writer.join(BLOCK_CHECK_SECONDS)
            assert writer.is_alive(), f"the {kind} did not wait for the departure: {outcome}"
        finally:
            tx.commit()
    writer.join(FINISH_TIMEOUT_SECONDS)
    assert not writer.is_alive()

    error = outcome.get("error")
    assert isinstance(error, AppError), f"the {kind} was accepted: {outcome}"
    assert error.status == 422
    if code is not None:
        assert error.code == code
    with engine.connect() as conn:
        counts = conn.execute(
            text(
                "SELECT (SELECT count(*) FROM app.expenses WHERE group_id = :g), "
                "(SELECT count(*) FROM app.payments WHERE group_id = :g)"
            ),
            {"g": house.id},
        ).one()
    assert tuple(counts) == (0, 0)


# ------------------------------------------------- C5: concurrent duplicates


def _race(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    first: Callable[[Session], object],
    second: Callable[[Session], object],
) -> dict[str, object]:
    """Run `first` up to its commit, then `second` in a thread, then commit `first`.

    `second` passes every "already exists?" check (it cannot see uncommitted rows) and
    blocks on the unique index until `first` commits; its outcome is returned.
    """
    outcome: dict[str, object] = {}

    def run() -> None:
        with Session(engine, expire_on_commit=False) as session:
            try:
                outcome["result"] = second(session)
            except AppError as exc:
                outcome["error"] = exc

    with Session(engine, expire_on_commit=False) as holder:
        real_commit = holder.commit
        # Keep `first`'s rows uncommitted: its own commit only flushes.
        monkeypatch.setattr(holder, "commit", holder.flush)
        first(holder)
        writer = threading.Thread(target=run)
        writer.start()
        writer.join(BLOCK_CHECK_SECONDS)
        try:
            assert writer.is_alive(), f"the second write did not wait: {outcome}"
        finally:
            real_commit()
    writer.join(FINISH_TIMEOUT_SECONDS)
    assert not writer.is_alive()
    return outcome


def _conflict_code(outcome: dict[str, object]) -> str:
    error = outcome.get("error")
    assert isinstance(error, AppError), f"expected a 409, got {outcome}"
    assert error.status == 409
    return error.code


def test_concurrent_category_name_is_409(
    committed_client: TestClient,
    make_user: Callable[[str], TestUser],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = make_house(committed_client, make_user)
    data = CategoryCreate(name="Gym")
    outcome = _race(
        engine,
        monkeypatch,
        lambda s: create_category(s, _juli(house), data),
        lambda s: create_category(s, _juli(house), CategoryCreate(name="gym")),
    )
    assert _conflict_code(outcome) == "category_exists"


def test_concurrent_category_rename_is_409(
    committed_client: TestClient,
    make_user: Callable[[str], TestUser],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = make_house(committed_client, make_user)
    groceries = uuid.UUID(house.categories["Groceries"])
    outcome = _race(
        engine,
        monkeypatch,
        lambda s: create_category(s, _juli(house), CategoryCreate(name="Gym")),
        lambda s: update_category(s, _juli(house), groceries, CategoryUpdate(name="Gym")),
    )
    assert _conflict_code(outcome) == "category_exists"


def test_concurrent_preset_keyword_is_409(
    committed_client: TestClient,
    make_user: Callable[[str], TestUser],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = make_house(committed_client, make_user)
    groceries = uuid.UUID(house.categories["Groceries"])
    outcome = _race(
        engine,
        monkeypatch,
        lambda s: create_category_preset(
            s, _juli(house), CategoryPresetCreate(keyword="mercadona", category_id=groceries)
        ),
        lambda s: create_category_preset(
            s, _juli(house), CategoryPresetCreate(keyword="Mercadona", category_id=groceries)
        ),
    )
    assert _conflict_code(outcome) == "preset_exists"


def test_concurrent_expense_retry_returns_the_stored_one(
    committed_client: TestClient,
    make_user: Callable[[str], TestUser],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same expense sent twice at once: one creates it, the other gets it back (200)."""
    house = make_house(committed_client, make_user)
    data = ExpenseCreate(
        id=uuid.uuid4(),
        amount_cents=3000,
        description="Cena",
        payer_member_id=uuid.UUID(house.members["Juli"]),
        expense_date=date(2026, 11, 27),
    )
    outcome = _race(
        engine,
        monkeypatch,
        lambda s: create_expense(s, _juli(house), data),
        lambda s: create_expense(s, _juli(house), data),
    )
    result = outcome.get("result")
    assert result is not None and getattr(result, "status", None) == 200, outcome


def test_concurrent_expense_with_other_payload_is_id_conflict(
    committed_client: TestClient,
    make_user: Callable[[str], TestUser],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = make_house(committed_client, make_user)
    data = ExpenseCreate(
        id=uuid.uuid4(),
        amount_cents=3000,
        description="Cena",
        payer_member_id=uuid.UUID(house.members["Juli"]),
        expense_date=date(2026, 11, 27),
    )
    other = data.model_copy(update={"amount_cents": 4000})
    outcome = _race(
        engine,
        monkeypatch,
        lambda s: create_expense(s, _juli(house), data),
        lambda s: create_expense(s, _juli(house), other),
    )
    assert _conflict_code(outcome) == "id_conflict"


def test_concurrent_payment_retry_returns_the_stored_one(
    committed_client: TestClient,
    make_user: Callable[[str], TestUser],
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    house = make_house(committed_client, make_user)
    payment = PaymentCreate(
        id=uuid.uuid4(),
        from_member_id=uuid.UUID(house.members["Juli"]),
        to_member_id=uuid.UUID(house.members["Ana"]),
        amount_cents=1000,
        method="bizum",
    )
    outcome = _race(
        engine,
        monkeypatch,
        lambda s: record_payment(s, _juli(house), payment),
        lambda s: record_payment(s, _juli(house), payment),
    )
    result = outcome.get("result")
    assert isinstance(result, tuple) and result[0] == 200, outcome
