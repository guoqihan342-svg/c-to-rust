from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from .context_frontier_state import (
    FRONTIER_READY, context_frontier_schedule_binding,
    validate_context_frontier_schedule_binding,
)
from .ledger_context_frontier_authority import (
    assert_context_frontier_projection,
)
from .ledger_security import LeaseConflict


def require_ready_context_frontier(
    connection: sqlite3.Connection, *, run_id: str, unit_id: str,
    expected: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    present = connection.execute(
        """select 1 from context_frontiers where run_id=? and unit_id=?""",
        (run_id, unit_id),
    ).fetchone()
    if present is None:
        if expected is not None:
            raise LeaseConflict("context frontier binding was supplied for a legacy unit")
        return None
    if expected is None:
        raise LeaseConflict("portfolio-bound lease requires a context frontier binding")
    try:
        claimed = validate_context_frontier_schedule_binding(expected)
        current = context_frontier_schedule_binding(
            assert_context_frontier_projection(connection, run_id, unit_id)
        )
    except (TypeError, ValueError) as error:
        raise LeaseConflict("context frontier binding is invalid") from error
    if claimed != current:
        raise LeaseConflict("context frontier binding is stale")
    if current["status"] != FRONTIER_READY:
        raise LeaseConflict("context frontier is not ready")
    return current


def context_frontier_for_unit_state(
    connection: sqlite3.Connection, *, run_id: str, unit_id: str,
) -> dict[str, Any] | None:
    present = connection.execute(
        """select 1 from context_frontiers where run_id=? and unit_id=?""",
        (run_id, unit_id),
    ).fetchone()
    if present is None:
        return None
    return context_frontier_schedule_binding(
        assert_context_frontier_projection(connection, run_id, unit_id)
    )


def reject_split_lease_for_context_frontier(
    connection: sqlite3.Connection, *, run_id: str, unit_id: str,
) -> None:
    if connection.execute(
        """select 1 from context_frontiers where run_id=? and unit_id=?""",
        (run_id, unit_id),
    ).fetchone():
        raise LeaseConflict(
            "portfolio-bound workers require atomic begin_worker_attempt",
        )


def require_attempt_context_frontier(
    connection: sqlite3.Connection, *, run_id: str, unit_id: str,
    attempt_metadata: Mapping[str, Any],
) -> None:
    present = connection.execute(
        """select 1 from context_frontiers where run_id=? and unit_id=?""",
        (run_id, unit_id),
    ).fetchone()
    claim = attempt_metadata.get("launch_claim")
    if present is None:
        if claim is not None:
            raise LeaseConflict("legacy attempt carries a context frontier claim")
        return
    if not isinstance(claim, Mapping):
        raise LeaseConflict("portfolio-bound attempt lost its launch claim")
    expected = claim.get("context_frontier")
    require_ready_context_frontier(
        connection, run_id=run_id, unit_id=unit_id,
        expected=expected if isinstance(expected, Mapping) else None,
    )


__all__ = [
    "context_frontier_for_unit_state", "reject_split_lease_for_context_frontier",
    "require_attempt_context_frontier", "require_ready_context_frontier",
]
