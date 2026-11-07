"""TS <-> Python parity: run every shared vector in packages/domain-vectors."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from split_ranch.domain import (
    DomainError,
    LedgerExpense,
    NetEntry,
    Share,
    SplitParticipant,
    allocate,
    compute_balances,
    resolve_shares,
    settle,
)

# tests/parity/test_vectors.py -> parents[4] is the repository root.
VECTORS_DIR = Path(
    os.environ.get(
        "SPLIT_RANCH_VECTORS_DIR",
        Path(__file__).resolve().parents[4] / "packages" / "domain-vectors",
    )
)

KNOWN_FILES = {"allocate.json", "resolve_shares.json", "balances.json", "settle.json"}


def _load(name: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((VECTORS_DIR / name).read_text(encoding="utf-8"))
    return data


def _cases(name: str) -> list[Any]:
    return [pytest.param(case, id=case["name"]) for case in _load(name)]


def _run_allocate(case: dict[str, Any]) -> Any:
    return allocate(case["total"], case["ratios"])


def _run_resolve(case: dict[str, Any]) -> Any:
    inp = case["input"]
    participants = [
        SplitParticipant(
            id=p["id"],
            weight=p.get("weight"),
            basis_points=p.get("basis_points"),
            exact_cents=p.get("exact_cents"),
        )
        for p in inp["participants"]
    ]
    shares = resolve_shares(inp["amount_cents"], inp["payer_id"], inp["split_type"], participants)
    return [{"id": s.id, "amount_cents": s.amount_cents} for s in shares]


def _run_balances(case: dict[str, Any]) -> Any:
    expenses = [
        LedgerExpense(
            payer_id=e["payer_id"],
            amount_cents=e["amount_cents"],
            shares=[Share(s["id"], s["amount_cents"]) for s in e["shares"]],
            personal=bool(e.get("personal", False)),
        )
        for e in case["expenses"]
    ]
    return [
        {
            "id": b.id,
            "paid_cents": b.paid_cents,
            "owed_cents": b.owed_cents,
            "net_cents": b.net_cents,
        }
        for b in compute_balances(case["member_order"], expenses)
    ]


def _run_settle(case: dict[str, Any]) -> Any:
    transfers = settle([NetEntry(n["id"], n["net_cents"]) for n in case["nets"]])
    return [
        {"from_id": t.from_id, "to_id": t.to_id, "amount_cents": t.amount_cents} for t in transfers
    ]


def _check(case: dict[str, Any], run: Any) -> None:
    assert ("expected" in case) != ("error" in case), "vector needs exactly one of expected/error"
    if "error" in case:
        with pytest.raises(DomainError) as exc:
            run(case)
        assert exc.value.code == case["error"]
    else:
        assert run(case) == case["expected"]


def test_vectors_dir_has_all_files() -> None:
    present = {p.name for p in VECTORS_DIR.glob("*.json") if p.name != "package.json"}
    assert present >= KNOWN_FILES
    unknown = present - KNOWN_FILES
    assert not unknown, f"unhandled vector files: {sorted(unknown)}"


@pytest.mark.parametrize("case", _cases("allocate.json"))
def test_allocate_vectors(case: dict[str, Any]) -> None:
    _check(case, _run_allocate)


@pytest.mark.parametrize("case", _cases("resolve_shares.json"))
def test_resolve_shares_vectors(case: dict[str, Any]) -> None:
    _check(case, _run_resolve)


@pytest.mark.parametrize("case", _cases("balances.json"))
def test_balances_vectors(case: dict[str, Any]) -> None:
    _check(case, _run_balances)


@pytest.mark.parametrize("case", _cases("settle.json"))
def test_settle_vectors(case: dict[str, Any]) -> None:
    _check(case, _run_settle)
