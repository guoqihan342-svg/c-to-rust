from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .ledger_schema import _json, _now_text, _require_repo_path, _require_sha256, atomic
from .ledger_security import LedgerError
from .ledger_transition_authority import TransitionAuthority, load_unit_projection
from .ledger_transition_commands import worker_command_started_command
from .runtime_prelaunch_cancel import PrelaunchCancellationMixin


REQUIRED_ASSIGNMENT_FIELDS = {
    "authority", "context", "dependencies", "group_id", "group_sha256",
    "isolated_out_root", "launch_policy", "ledger_binding", "max_attempts",
    "out_root", "role", "run_id", "runtime_roots", "unit_id", "wave_index",
    "worker_id",
}


def compute_portfolio_binding(portfolio: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(portfolio, Mapping):
        raise ValueError("portfolio must be an object")
    claimed = portfolio.get("plan_sha256")
    payload = {key: value for key, value in portfolio.items() if key != "plan_sha256"}
    if not isinstance(claimed, str) or content_sha256(payload) != claimed:
        raise ValueError("portfolio plan_sha256 drifted")
    run_id = _text(portfolio, "run_id")
    dag_sha256 = _sha(portfolio, "dag_sha256")
    assignments = portfolio.get("assignments")
    units = portfolio.get("ledger_units")
    if not isinstance(assignments, list) or not isinstance(units, list):
        raise ValueError("portfolio assignments/ledger_units are invalid")
    records: list[dict[str, str]] = []
    seen_workers: set[str] = set()
    seen_roles: set[tuple[str, str]] = set()
    for value in assignments:
        if not isinstance(value, Mapping) or not REQUIRED_ASSIGNMENT_FIELDS <= set(value):
            raise ValueError("portfolio assignment fields are incomplete")
        worker_id = _text(value, "worker_id")
        unit_id = _text(value, "unit_id")
        group_id = _text(value, "group_id")
        role = _text(value, "role")
        if group_id != unit_id or value.get("run_id") != run_id:
            raise ValueError("assignment run/group/unit identity drifted")
        if worker_id in seen_workers or (unit_id, role) in seen_roles:
            raise ValueError("assignment worker/unit-role identity is not unique")
        seen_workers.add(worker_id)
        seen_roles.add((unit_id, role))
        _validate_ledger_binding(value)
        roots = value.get("runtime_roots")
        if (
            not isinstance(roots, Mapping)
            or roots.get("out") != value.get("out_root")
            or value.get("isolated_out_root") != value.get("out_root")
        ):
            raise ValueError("assignment runtime roots are inconsistent")
        records.append({
            "worker_id": worker_id,
            "unit_id": unit_id,
            "role": role,
            "assignment_sha256": content_sha256(value),
        })
    unit_records: list[dict[str, Any]] = []
    seen_units: set[str] = set()
    for value in units:
        if not isinstance(value, Mapping):
            raise ValueError("portfolio ledger unit is invalid")
        unit_id = _text(value, "unit_id")
        if unit_id in seen_units or value.get("group_id") != unit_id:
            raise ValueError("portfolio unit/group identity is invalid")
        seen_units.add(unit_id)
        unit_records.append({
            "unit_id": unit_id,
            "group_id": unit_id,
            "wave_index": value.get("wave_index"),
            "content_sha256": _sha(value, "content_sha256"),
        })
    if {item["unit_id"] for item in records} - seen_units:
        raise ValueError("portfolio assignment references an unknown unit")
    records.sort(key=lambda item: (item["unit_id"], item["role"], item["worker_id"]))
    unit_records.sort(key=lambda item: item["unit_id"])
    binding = {
        "schema_version": 1,
        "run_id": run_id,
        "dag_sha256": dag_sha256,
        "plan_sha256": claimed,
        "assignments": records,
        "assignment_set_sha256": content_sha256(records),
        "units": unit_records,
        "unit_set_sha256": content_sha256(unit_records),
    }
    binding["binding_sha256"] = content_sha256(binding)
    return binding


class RuntimeBindingMixin(PrelaunchCancellationMixin):
    def require_portfolio_binding(self, portfolio: Mapping[str, Any]) -> dict[str, Any]:
        expected = compute_portfolio_binding(portfolio)
        with self.connect() as connection:
            run = connection.execute(
                "select status,dag_sha256,metadata_json from project_runs where run_id=?",
                (expected["run_id"],),
            ).fetchone()
            if not run or run["status"] != "active" or run["dag_sha256"] != expected["dag_sha256"]:
                raise LedgerError("dispatch requires the active hash-bound project run")
            metadata = _object_json(run["metadata_json"], "run metadata")
            if metadata.get("runtime_binding") != expected:
                raise LedgerError("portfolio does not match the immutable ledger binding")
            assignments = connection.execute(
                """select unit_id,worker_id,role,out_root,max_attempts from assignments
                   where run_id=? order by unit_id,role,worker_id""",
                (expected["run_id"],),
            ).fetchall()
            units = connection.execute(
                """select unit_id,group_id,wave_index,content_sha256 from migration_units
                   where run_id=? order by unit_id""", (expected["run_id"],),
            ).fetchall()
        _verify_ledger_rows(portfolio, assignments, units)
        return expected

    def bind_attempt_request(
        self, *, attempt_id: str, owner: str, fencing_token: int,
        request_path: str, request_sha256: str, effective_input_sha256: str,
    ) -> None:
        with self.connect() as connection, atomic(connection):
            attempt = self._running_attempt(connection, attempt_id, owner, fencing_token)
            row = connection.execute(
                "select metadata_json,input_sha256 from attempts where attempt_id=?", (attempt_id,),
            ).fetchone()
            metadata = _object_json(row["metadata_json"], "attempt metadata")
            if metadata.get("request_sha256") is not None:
                raise LedgerError("attempt request is already bound")
            if attempt["run_id"] != metadata.get("run_id") or attempt["unit_id"] != metadata.get("unit_id"):
                raise LedgerError("attempt metadata identity drifted")
            if row["input_sha256"] != effective_input_sha256:
                raise LedgerError("attempt effective input SHA-256 drifted")
            metadata.update({
                "request_path": _require_repo_path(request_path, "request_path"),
                "request_sha256": _require_sha256(request_sha256, "request_sha256"),
                "effective_input_sha256": _require_sha256(
                    effective_input_sha256, "effective_input_sha256"
                ),
            })
            connection.execute(
                "update attempts set metadata_json=? where attempt_id=?",
                (_json(metadata), attempt_id),
            )

    def bound_attempt(
        self, *, attempt_id: str, owner: str, fencing_token: int,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            attempt = self._running_attempt(connection, attempt_id, owner, fencing_token)
            row = connection.execute(
                """select t.*,a.out_root,l.expires_at,l.heartbeat_at
                   from attempts t join assignments a on a.run_id=t.run_id and a.unit_id=t.unit_id
                     and a.worker_id=t.worker_id and a.role=t.role
                   join leases l on l.run_id=t.run_id and l.unit_id=t.unit_id
                   where t.attempt_id=?""", (attempt_id,),
            ).fetchone()
        result = dict(row)
        result["metadata"] = _object_json(result["metadata_json"], "attempt metadata")
        return result

    def bind_attempt_preflight(
        self, *, attempt_id: str, owner: str, fencing_token: int,
        preflight_path: str, preflight_sha256: str,
    ) -> None:
        with self.connect() as connection, atomic(connection):
            self._running_attempt(connection, attempt_id, owner, fencing_token)
            row = connection.execute(
                "select metadata_json from attempts where attempt_id=?", (attempt_id,),
            ).fetchone()
            metadata = _object_json(row[0], "attempt metadata")
            if metadata.get("command_started") is True:
                raise LedgerError("started worker command cannot bind preflight evidence")
            if metadata.get("preflight_sha256") is not None:
                raise LedgerError("attempt preflight evidence is already bound")
            metadata.update({
                "preflight_path": _require_repo_path(preflight_path, "preflight_path"),
                "preflight_sha256": _require_sha256(
                    preflight_sha256, "preflight_sha256"
                ),
            })
            connection.execute(
                "update attempts set metadata_json=? where attempt_id=?",
                (_json(metadata), attempt_id),
            )

    def mark_command_started(
        self, *, attempt_id: str, owner: str, fencing_token: int,
    ) -> None:
        with self.connect() as connection, atomic(connection):
            attempt = self._running_attempt(connection, attempt_id, owner, fencing_token)
            row = connection.execute(
                "select metadata_json from attempts where attempt_id=?", (attempt_id,),
            ).fetchone()
            metadata = _object_json(row[0], "attempt metadata")
            if metadata.get("command_started") is True:
                raise LedgerError("worker command was already started for this attempt")
            timestamp = _now_text()
            metadata["command_started"] = True
            metadata["command_started_at"] = timestamp
            connection.execute(
                "update attempts set metadata_json=? where attempt_id=?", (_json(metadata), attempt_id),
            )
            run_id, unit_id = str(attempt["run_id"]), str(attempt["unit_id"])
            command = worker_command_started_command(
                run_id=run_id, unit_id=unit_id, attempt_id=attempt_id, fencing_token=fencing_token,
                expected=load_unit_projection(connection, run_id, unit_id), metadata=metadata)
            TransitionAuthority(connection).apply(command, created_at=timestamp)

def _verify_ledger_rows(
    portfolio: Mapping[str, Any], assignments: Any, units: Any,
) -> None:
    expected_assignments = sorted(
        (str(item["unit_id"]), str(item["worker_id"]), str(item["role"]),
         str(item["out_root"]), int(item["max_attempts"]))
        for item in portfolio["assignments"]
    )
    expected_units = sorted(
        (str(item["unit_id"]), str(item["group_id"]), int(item["wave_index"]),
         str(item["content_sha256"])) for item in portfolio["ledger_units"]
    )
    if sorted(tuple(row) for row in assignments) != expected_assignments:
        raise LedgerError("ledger assignments drifted from the portfolio")
    if sorted(tuple(row) for row in units) != expected_units:
        raise LedgerError("ledger units drifted from the portfolio")


def _validate_ledger_binding(assignment: Mapping[str, Any]) -> None:
    binding = assignment.get("ledger_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("assignment ledger_binding is invalid")
    claimed = binding.get("binding_sha256")
    payload = {key: value for key, value in binding.items() if key != "binding_sha256"}
    if content_sha256(payload) != claimed:
        raise ValueError("assignment ledger_binding SHA-256 drifted")
    expected = {
        "run_id": assignment.get("run_id"), "unit_id": assignment.get("unit_id"),
        "group_id": assignment.get("group_id"), "role": assignment.get("role"),
        "worker_id": assignment.get("worker_id"), "lease_owner": assignment.get("worker_id"),
        "isolated_out_root": assignment.get("isolated_out_root"),
    }
    if payload != expected:
        raise ValueError("assignment ledger_binding fields drifted")


def _object_json(value: Any, label: str) -> dict[str, Any]:
    try:
        result = json.loads(value) if isinstance(value, str) else None
    except json.JSONDecodeError as error:
        raise LedgerError(f"{label} is invalid JSON") from error
    if not isinstance(result, dict):
        raise LedgerError(f"{label} must be an object")
    return result


def _text(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{key} must be a non-empty string")
    return result


def _sha(value: Mapping[str, Any], key: str) -> str:
    return _require_sha256(_text(value, key), key)


__all__ = ["RuntimeBindingMixin", "compute_portfolio_binding"]
