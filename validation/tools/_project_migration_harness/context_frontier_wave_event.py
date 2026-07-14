from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256


def wave_invalidation_command_id(unit_id: str, wave_artifact_sha256: str) -> str:
    if not isinstance(unit_id, str) or not unit_id:
        raise ValueError("context frontier wave event unit is invalid")
    if not isinstance(wave_artifact_sha256, str) or len(wave_artifact_sha256) != 64:
        raise ValueError("context frontier wave event artifact SHA-256 is invalid")
    return "selection-invalidated:" + content_sha256({
        "unit_id": unit_id,
        "wave_input_sha256": wave_artifact_sha256,
    })


def pending_wave_artifact_sha256(
    ledger: Any, projection: Mapping[str, Any],
) -> str | None:
    run_id = projection.get("head", {}).get("run_id")
    unit_id = projection.get("unit_id")
    head_sha256 = projection.get("head_sha256")
    if not all(isinstance(item, str) and item for item in (run_id, unit_id, head_sha256)):
        raise ValueError("context frontier pending projection is invalid")
    with ledger.connect() as connection:
        row = connection.execute(
            """select command_kind,command_id,evidence_sha256,to_head_sha256
               from context_frontier_events where run_id=? and unit_id=?
               order by event_id desc limit 1""",
            (run_id, unit_id),
        ).fetchone()
    if row is None or row["command_kind"] != "selection_invalidated":
        return None
    evidence = str(row["evidence_sha256"])
    if (
        row["to_head_sha256"] != head_sha256
        or row["command_id"] != wave_invalidation_command_id(str(unit_id), evidence)
    ):
        return None
    return evidence


__all__ = ["pending_wave_artifact_sha256", "wave_invalidation_command_id"]
