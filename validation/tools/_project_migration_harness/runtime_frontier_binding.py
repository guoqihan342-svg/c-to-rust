from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .ledger_context_frontier import prepare_portfolio_frontiers
from .ledger_context_frontier_authority import (
    assert_context_frontier_projection,
)
from .ledger_security import LedgerError


def portfolio_frontier_binding_records(
    portfolio: Mapping[str, Any], *, run_id: str, unit_ids: Sequence[str],
) -> list[dict[str, Any]]:
    rows = prepare_portfolio_frontiers(
        portfolio, run_id=run_id, unit_ids=unit_ids,
    )
    return [
        {
            "unit_id": row["unit_id"],
            "initial_status": row["initial_status"],
            "initial_head_sha256": row["initial_head_sha256"],
        }
        for row in rows
    ]


def verify_context_frontier_binding(
    connection: sqlite3.Connection, *, run_id: str,
    expected: Sequence[Mapping[str, Any]],
) -> None:
    actual = [tuple(row) for row in connection.execute(
        """select unit_id,initial_status,initial_head_sha256
           from context_frontiers where run_id=? order by unit_id""", (run_id,),
    ).fetchall()]
    wanted = sorted(
        (str(row["unit_id"]), str(row["initial_status"]),
         str(row["initial_head_sha256"]))
        for row in expected
    )
    if actual != wanted:
        raise LedgerError("ledger context frontiers drifted from the portfolio")
    for unit_id, _status, _digest in wanted:
        assert_context_frontier_projection(connection, run_id, unit_id)


def context_frontier_set_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    return content_sha256(list(records))


__all__ = [
    "context_frontier_set_sha256", "portfolio_frontier_binding_records",
    "verify_context_frontier_binding",
]
