from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .context_frontier_state import validate_context_frontier_head
from .context_frontier_wave_event import wave_invalidation_command_id
from .ledger_context_frontier_authority import (
    ContextFrontierAuthority, _ContextFrontierCommand,
    assert_context_frontier_projection,
)
from .ledger_schema import _json, atomic
from .ledger_security import LedgerError


class ContextFrontierLedgerMixin:
    def context_frontier_states(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            unit_ids = [str(row[0]) for row in connection.execute(
                """select unit_id from context_frontiers
                   where run_id=? order by unit_id""",
                (run_id,),
            ).fetchall()]
            projections = [
                assert_context_frontier_projection(connection, run_id, unit_id)
                for unit_id in unit_ids
            ]
        return [
            {"unit_id": unit_id, **_public_projection(projection)}
            for unit_id, projection in zip(unit_ids, projections)
        ]

    def _commit_context_refresh(
        self, permit: Any, *, harness_root: Path,
    ) -> dict[str, Any]:
        from .context_frontier_refresh_reopen import (
            reopen_host_context_refresh_permit,
        )

        with self.connect() as connection, atomic(connection):
            binding = reopen_host_context_refresh_permit(
                permit, harness_root=harness_root,
            )
            run = connection.execute(
                "select status,metadata_json from project_runs where run_id=?",
                (binding["run_id"],),
            ).fetchone()
            if run is None or run["status"] != "active":
                raise LedgerError("context refresh requires an active run")
            try:
                metadata = json.loads(run["metadata_json"])
            except (TypeError, json.JSONDecodeError) as error:
                raise LedgerError("context refresh run metadata is invalid") from error
            runtime = metadata.get("runtime_binding") if isinstance(metadata, Mapping) else None
            if (
                not isinstance(runtime, Mapping)
                or runtime.get("plan_sha256") != binding["plan_sha256"]
            ):
                raise LedgerError("context refresh plan binding drifted")
            result = ContextFrontierAuthority(connection).apply(
                _ContextFrontierCommand(
                    command_kind="selection_ready",
                    command_id="selection-ready:" + str(binding["overlay"]["sha256"]),
                    run_id=str(binding["run_id"]),
                    unit_id=str(binding["unit_id"]),
                    expected_status=str(binding["expected_status"]),
                    expected_version=int(binding["expected_version"]),
                    expected_head_sha256=str(binding["expected_head_sha256"]),
                    target_head=binding["target_head"],
                    evidence_sha256=str(binding["overlay"]["sha256"]),
                )
            )
        return {
            "applied": result.applied,
            "event_id": result.event_id,
            "previous": _public_projection(result.previous),
            "current": _public_projection(result.current),
        }

    def _commit_context_wave_invalidations(
        self, permits: Sequence[Any], *, harness_root: Path,
    ) -> list[dict[str, Any]]:
        from .context_frontier_wave_permit import (
            _host_context_frontier_wave_binding,
            _reopen_host_context_frontier_wave_permit,
        )

        if not permits:
            raise ValueError("context frontier wave permits are empty")
        with self.connect() as connection, atomic(connection):
            bindings = []
            for permit in permits:
                claimed = _host_context_frontier_wave_binding(permit)
                bindings.append(_reopen_host_context_frontier_wave_permit(
                    permit,
                    harness_root=harness_root,
                    current_projection=assert_context_frontier_projection(
                        connection, claimed["run_id"], claimed["unit_id"],
                    ),
                ))
            identities = {
                (item["run_id"], item["next_wave_index"], item["wave_input"]["sha256"])
                for item in bindings
            }
            expected_units = set(bindings[0]["wave_input_payload"]["next_unit_ids"])
            if (
                len(identities) != 1
                or {item["unit_id"] for item in bindings} != expected_units
                or len(bindings) != len(expected_units)
            ):
                raise LedgerError("context frontier wave permit set drifted")
            run_id = str(bindings[0]["run_id"])
            run = connection.execute(
                "select status,dag_sha256 from project_runs where run_id=?", (run_id,),
            ).fetchone()
            units = {
                str(row["unit_id"]): row for row in connection.execute(
                    """select unit_id,wave_index,content_sha256 from migration_units
                       where run_id=?""", (run_id,),
                ).fetchall()
            }
            if run is None or run["status"] != "active":
                raise LedgerError("context frontier wave requires an active run")
            results = []
            for binding in sorted(bindings, key=lambda item: item["unit_id"]):
                unit = units.get(str(binding["unit_id"]))
                if (
                    run["dag_sha256"] != binding["dag_sha256"]
                    or unit is None
                    or int(unit["wave_index"]) != binding["next_wave_index"]
                    or unit["content_sha256"] != binding["group_sha256"]
                ):
                    raise LedgerError("context frontier wave ledger binding drifted")
                command_id = wave_invalidation_command_id(
                    str(binding["unit_id"]), str(binding["wave_input"]["sha256"]),
                )
                results.append(ContextFrontierAuthority(connection).apply(
                    _ContextFrontierCommand(
                        command_kind="selection_invalidated",
                        command_id=command_id,
                        run_id=run_id,
                        unit_id=str(binding["unit_id"]),
                        expected_status=str(binding["expected_status"]),
                        expected_version=int(binding["expected_version"]),
                        expected_head_sha256=str(binding["expected_head_sha256"]),
                        target_head=binding["target_head"],
                        evidence_sha256=str(binding["wave_input"]["sha256"]),
                    )
                ))
        return [{
            "applied": result.applied,
            "event_id": result.event_id,
            "previous": _public_projection(result.previous),
            "current": _public_projection(result.current),
        } for result in results]


def prepare_portfolio_frontiers(
    portfolio: Mapping[str, Any] | None, *, run_id: str,
    unit_ids: Sequence[str],
) -> list[dict[str, Any]]:
    if portfolio is None or "context_frontiers" not in portfolio:
        return []
    values = portfolio.get("context_frontiers")
    if not isinstance(values, list):
        raise ValueError("portfolio context_frontiers must be a list")
    known = set(unit_ids)
    seen: set[str] = set()
    result = []
    for value in values:
        if not isinstance(value, Mapping) or set(value) != {
            "unit_id", "group_id", "initial_status", "initial_head",
            "initial_head_sha256",
        }:
            raise ValueError("portfolio context frontier shape is invalid")
        unit_id = value.get("unit_id")
        if (
            not isinstance(unit_id, str) or not unit_id or unit_id in seen
            or unit_id not in known or value.get("group_id") != unit_id
        ):
            raise ValueError("portfolio context frontier identity is invalid")
        head = validate_context_frontier_head(value.get("initial_head"))
        digest = content_sha256(head)
        if (
            head["run_id"] != run_id or head["unit_id"] != unit_id
            or value.get("initial_status") != head["status"]
            or value.get("initial_head_sha256") != digest
        ):
            raise ValueError("portfolio context frontier binding drifted")
        seen.add(unit_id)
        result.append({
            "unit_id": unit_id, "initial_status": head["status"],
            "initial_head": head, "initial_head_sha256": digest,
        })
    assignments = portfolio.get("assignments", [])
    if not isinstance(assignments, list):
        raise ValueError("portfolio assignments must be a list")
    catalog_backed = {
        str(item.get("group_id"))
        for item in assignments if isinstance(item, Mapping)
        and isinstance(item.get("context"), Mapping)
        and isinstance(item["context"].get("catalog"), Mapping)
    }
    if seen != catalog_backed:
        raise ValueError("portfolio context frontiers do not cover catalog-backed assignments")
    return sorted(result, key=lambda item: item["unit_id"])


def insert_context_frontiers(
    connection: sqlite3.Connection, *, run_id: str,
    rows: Sequence[Mapping[str, Any]], now: str,
) -> None:
    for row in rows:
        connection.execute(
            """insert into context_frontiers(
               run_id,unit_id,initial_status,status,state_version,initial_head_json,
               initial_head_sha256,head_json,head_sha256,updated_at)
               values (?,?,?,?,0,?,?,?,?,?)""",
            (
                run_id, row["unit_id"], row["initial_status"],
                row["initial_status"], _json(row["initial_head"]),
                row["initial_head_sha256"], _json(row["initial_head"]),
                row["initial_head_sha256"], now,
            ),
        )


def verify_initial_context_frontiers(
    connection: sqlite3.Connection, *, run_id: str,
    expected: Sequence[Mapping[str, Any]],
) -> None:
    actual = [tuple(row) for row in connection.execute(
        """select unit_id,initial_status,initial_head_sha256
           from context_frontiers where run_id=? order by unit_id""", (run_id,),
    ).fetchall()]
    wanted = [
        (row["unit_id"], row["initial_status"], row["initial_head_sha256"])
        for row in expected
    ]
    if actual != wanted:
        raise LedgerError("run_id already exists with different context frontier inputs")
    for row in expected:
        projection = assert_context_frontier_projection(
            connection, run_id, str(row["unit_id"]),
        )
        if projection.version < 0:
            raise LedgerError("context frontier version is invalid")


def _public_projection(value: Any) -> dict[str, Any]:
    return {
        "status": value.status, "state_version": value.version,
        "head": value.head, "head_sha256": value.head_sha256,
    }


__all__ = [
    "ContextFrontierLedgerMixin", "insert_context_frontiers",
    "prepare_portfolio_frontiers", "verify_initial_context_frontiers",
]
