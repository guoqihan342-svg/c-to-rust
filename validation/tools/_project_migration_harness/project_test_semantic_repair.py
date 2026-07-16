from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .controller_gates import record_candidate_gate
from .ledger import ProjectLedger


def register_project_test_candidate_repairs(
    *, ledger: ProjectLedger, run_id: str, out_root: Any, out_root_rel: str,
    candidate_set_sha256: str, project_record_id: str,
    candidate_members: Sequence[Mapping[str, Any]],
    rust_project_ir: Mapping[str, Any], mapping: Mapping[str, Any],
    oracle: Mapping[str, Any],
) -> dict[str, Any]:
    unit_ids = _affected_units(rust_project_ir, mapping, oracle)
    members = {
        str(item["unit_id"]): item for item in candidate_members
        if isinstance(item, Mapping) and isinstance(item.get("unit_id"), str)
    }
    if not unit_ids or not unit_ids <= set(members):
        return _blocked("project_test_repair_attribution_unavailable")
    diagnostics = model_safe_project_failure_diagnostics(oracle)
    records = []
    failures = []
    for unit_id in sorted(unit_ids):
        member = members[unit_id]
        artifact_id = str(member["artifact_id"])
        record_id = "host-project-oracle-" + content_sha256({
            "candidate_set_sha256": candidate_set_sha256,
            "unit_id": unit_id, "artifact_id": artifact_id,
            "project_record_id": project_record_id,
        })[:24]
        records.append(record_candidate_gate(
            ledger=ledger, out_root=out_root, out_root_rel=out_root_rel,
            run_id=run_id, unit_id=unit_id,
            candidate_artifact_id=artifact_id, record_id=record_id,
            kind="verifier", gate_family="oracle-replay-diff", status="failed",
            verifier_id="host-derived", diagnostics=diagnostics,
            candidate_set_sha256=candidate_set_sha256,
            project_record_id=project_record_id, defer_transition=True,
        ))
        failures.append({
            "unit_id": unit_id, "candidate_artifact_id": artifact_id,
            "failed_record_id": record_id,
        })
    ledger.mark_verification_failures(
        run_id=run_id, failures=failures,
        expected_candidate_set_sha256=candidate_set_sha256,
    )
    return {
        "schema_version": 1, "status": "repair-required",
        "affected_unit_ids": sorted(unit_ids), "candidate_gate_records": records,
        "failure_signature_sha256": content_sha256(diagnostics),
        "answer_values_withheld": True, "semantic_gate": False,
    }


def model_safe_project_failure_diagnostics(
    oracle: Mapping[str, Any],
) -> list[dict[str, str]]:
    evidence = oracle.get("evidence")
    details = evidence.get("failure_details") if isinstance(evidence, Mapping) else None
    codes: set[str] = set()
    if isinstance(details, list):
        for detail in details:
            if not isinstance(detail, Mapping):
                continue
            baseline, candidate = detail.get("oracle"), detail.get("replay")
            if not isinstance(baseline, Mapping) or not isinstance(candidate, Mapping):
                continue
            for field, channel in (
                ("status", "status"), ("exit_code", "exit"),
                ("signal", "signal"), ("timed_out", "timeout"),
                ("oversized", "oversized"), ("stdout_sha256", "stdout"),
                ("stderr_sha256", "stderr"),
            ):
                if baseline.get(field) != candidate.get(field):
                    codes.add(f"project-channel.{channel}")
            process_class = _candidate_process_class(candidate)
            if process_class != "completed-zero-exit":
                codes.add(f"project-process.{process_class}")
    if not codes:
        observation = oracle.get("observation")
        crash_count = observation.get("crash_count") if isinstance(
            observation, Mapping
        ) else None
        codes.add(
            "project-process-crash"
            if isinstance(crash_count, int) and crash_count
            else "project-logic-mismatch"
        )
    return [
        {"code": code, "stage": "project-oracle"}
        for code in sorted(codes)
    ][:32]


def _candidate_process_class(value: Mapping[str, Any]) -> str:
    if value.get("timed_out") is True:
        return "timeout"
    if value.get("oversized") is True:
        return "oversized"
    if value.get("signal") is not None:
        return "signal"
    if value.get("status") != "completed":
        return "blocked"
    if value.get("exit_code") != 0:
        return "nonzero-exit"
    return "completed-zero-exit"


def _affected_units(
    ir: Mapping[str, Any], mapping: Mapping[str, Any], oracle: Mapping[str, Any],
) -> set[str]:
    evidence = oracle.get("evidence")
    details = evidence.get("failure_details") if isinstance(evidence, Mapping) else None
    failed_tests = {
        str(item["test_id"]) for item in details or []
        if isinstance(item, Mapping) and isinstance(item.get("test_id"), str)
    }
    mappings = mapping.get("mappings")
    if not isinstance(mappings, list):
        return set()
    if isinstance(evidence, Mapping) and evidence.get("details_truncated") is True:
        source_targets = {str(item["source_target_id"]) for item in mappings}
    else:
        source_targets = {
            str(item["source_target_id"]) for item in mappings
            if isinstance(item, Mapping)
            and failed_tests.intersection(str(value) for value in item.get("test_ids", []))
        }
    targets = {
        str(item["build_ir_target_id"]): item for item in ir.get("targets", [])
        if isinstance(item, Mapping)
    }
    modules = {
        str(item["module_id"]): item for item in ir.get("modules", [])
        if isinstance(item, Mapping)
    }
    return {
        str(modules[module_id]["unit_id"])
        for source_target in source_targets
        for module_id in targets.get(source_target, {}).get("module_ids", [])
        if module_id in modules
    }


def _blocked(code: str) -> dict[str, Any]:
    return {
        "schema_version": 1, "status": "blocked", "blockers": [code],
        "affected_unit_ids": [], "candidate_gate_records": [],
        "answer_values_withheld": True, "semantic_gate": False,
    }


__all__ = [
    "model_safe_project_failure_diagnostics",
    "register_project_test_candidate_repairs",
]
