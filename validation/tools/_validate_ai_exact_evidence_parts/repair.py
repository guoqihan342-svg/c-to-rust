from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from validation.tools._ai_candidate_harness_parts.prompt_transport import (
    prompt_transport_contract,
)

from .io import EvidenceStore, fail, reject_accepted_proof, require_sha, sha256_file


REQUIRED_ROUND_BINDINGS = ("failure_facts", "prompt")
OPTIONAL_ROUND_BINDINGS = ("raw_response", "repair_artifact", "candidate", "validation_result")
GENERATOR_IDENTITY_FIELDS = (
    "tool",
    "provider",
    "logical_model",
    "resolved_model",
    "competition_eligible",
    "evaluation_scope",
    "agent",
    "variant",
)
REPAIR_SOURCE = "c2rust-repair"
REPAIR_EVIDENCE_KEY = "c2rust_repair"


def validate_c2rust_repair_audit(store: EvidenceStore, router: dict[str, Any]) -> int:
    candidates = router.get("candidate_set")
    duplicates = router.get("deduplicated_candidates")
    evidence = router.get("candidate_evidence")
    audits = router.get("candidate_source_audit")
    if not isinstance(candidates, list) or not isinstance(duplicates, list) or not isinstance(evidence, dict):
        return 0

    unique = _one_source(candidates, REPAIR_SOURCE)
    duplicate = _one_source(duplicates, REPAIR_SOURCE)
    audit = audits.get(REPAIR_EVIDENCE_KEY) if isinstance(audits, dict) else None
    if unique is None and duplicate is None and REPAIR_EVIDENCE_KEY not in evidence and audit is None:
        return 0
    if not isinstance(audit, dict):
        fail("c2rust_repair_audit_missing", "routed c2rust-repair requires source audit", path="router")
    reject_accepted_proof(audit, "router.candidate_source_audit.c2rust_repair")
    if audit.get("source") != REPAIR_SOURCE:
        fail("c2rust_repair_audit_source", "c2rust-repair audit source drifted", path="router")

    base_sha = require_sha(
        audit.get("base_candidate_sha256"),
        "router.candidate_source_audit.c2rust_repair.base_candidate_sha256",
    )
    repair_rounds = audit.get("repair_rounds")
    if isinstance(repair_rounds, bool) or not isinstance(repair_rounds, int) or not 0 <= repair_rounds <= 5:
        fail("c2rust_repair_round_count", "c2rust-repair rounds must be between 0 and 5", path="router")

    report_ref = audit.get("repair_report")
    if not isinstance(report_ref, dict) or report_ref.get("semantic_pass") is not False:
        fail("c2rust_repair_report_claim", "repair report reference must keep semantic_pass false", path="router")
    _require_same_directory_path(report_ref.get("path"), "router.c2rust_repair.repair_report")
    report_path, report = store.read_bound_json(report_ref, "router.c2rust_repair.repair_report")
    if report_path.parent != store.root or report_ref.get("status") != report.get("status"):
        fail("c2rust_repair_report_binding", "repair report reference drifted", path="router")
    reject_accepted_proof(report, "router.c2rust_repair.repair_report")
    ai_candidate = _one_source(candidates, "opencode-ai") or _one_source(
        duplicates,
        "opencode-ai",
    )
    _validate_report_shape(
        report,
        base_sha=base_sha,
        expected_generator=_router_generator_identity(ai_candidate),
    )
    rounds = report.get("rounds")
    if not isinstance(rounds, list) or len(rounds) != repair_rounds:
        fail("c2rust_repair_round_count", "repair report rounds differ from audit", path="router")
    for index, round_record in enumerate(rounds, 1):
        _validate_round(store, report_path, round_record, index)

    routed = unique if unique is not None else duplicate
    if unique is not None and duplicate is not None:
        fail("c2rust_repair_candidate_ambiguous", "repair cannot be unique and duplicate", path="router")
    if routed is None:
        if REPAIR_EVIDENCE_KEY in evidence or audit.get("status") != "repair_completed_without_candidate":
            fail("c2rust_repair_orphan", "non-routed repair audit/evidence drifted", path="router")
        if _report_has_bound_candidate(report):
            fail("c2rust_repair_orphan", "reopenable repair candidate was omitted from router", path="router")
        return repair_rounds

    routed_sha = require_sha(routed.get("artifact_sha256"), "router.c2rust_repair.artifact_sha256")
    final_sha = require_sha(
        audit.get("final_candidate_sha256"),
        "router.candidate_source_audit.c2rust_repair.final_candidate_sha256",
    )
    if final_sha != routed_sha:
        fail("c2rust_repair_final_candidate_drift", "repair audit final SHA differs from router", path="router")
    _validate_report_final_candidate(store, report_path, report, routed_sha)

    if unique is not None:
        if REPAIR_EVIDENCE_KEY not in evidence or audit.get("status") != "exact_gates_completed":
            fail("c2rust_repair_unique_audit", "unique repair candidate lacks exact audit/evidence", path="router")
        expected_reason = (
            "fresh_exact_gates_passed"
            if unique.get("decision") in {"selected", "eligible_not_selected"}
            else "fresh_exact_gates_failed"
        )
        if audit.get("reason") != expected_reason:
            fail("c2rust_repair_unique_audit", "repair exact result reason drifted", path="router")
    else:
        if REPAIR_EVIDENCE_KEY in evidence:
            fail("c2rust_repair_duplicate_evidence", "duplicate repair must not own exact evidence", path="router")
        if audit.get("status") != "duplicate" or audit.get("reason") != "duplicate_exact_artifact_sha256":
            fail("c2rust_repair_duplicate_audit", "duplicate repair audit drifted", path="router")
        if audit.get("duplicate_of") != duplicate.get("duplicate_of"):
            fail("c2rust_repair_duplicate_audit", "duplicate repair owner drifted", path="router")
    return repair_rounds


def _validate_report_shape(
    report: dict[str, Any],
    *,
    base_sha: str,
    expected_generator: dict[str, Any] | None,
) -> None:
    if report.get("schema_version") != 3 or report.get("artifact_label") != REPAIR_SOURCE:
        fail("c2rust_repair_report_identity", "repair report identity drifted", path="router")
    generator = report.get("generator")
    if (
        not isinstance(generator, dict)
        or generator.get("prompt_transport") != prompt_transport_contract()
    ):
        fail(
            "c2rust_repair_prompt_transport",
            "repair prompt transport drifted",
            path="router",
        )
    if expected_generator is None or any(
        generator.get(key) != value for key, value in expected_generator.items()
    ):
        fail(
            "c2rust_repair_generator_identity",
            "repair generator identity differs from the routed AI generator",
            path="router",
        )
    if report.get("input_source") != "c2rust-baseline":
        fail("c2rust_repair_input_source", "repair report input source drifted", path="router")
    boundary = report.get("claim_boundary")
    if not isinstance(boundary, dict) or (
        boundary.get("semantic_gate") is not False
        or boundary.get("semantic_pass") is not False
        or boundary.get("translation_coverage_numerator") != 0
    ) or report.get("semantic_pass") is True:
        fail("c2rust_repair_false_semantic_pass", "repair report cannot claim acceptance", path="router")
    initial = report.get("initial_candidate")
    if not isinstance(initial, dict) or initial.get("sha256") != base_sha:
        fail("c2rust_repair_base_candidate", "repair report baseline SHA drifted", path="router")


def _router_generator_identity(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    identity = {
        "tool": "opencode",
        "provider": candidate.get("provider"),
        "logical_model": candidate.get("logical_model"),
        "resolved_model": candidate.get("resolved_model"),
        "competition_eligible": candidate.get("competition_eligible"),
        "evaluation_scope": candidate.get("evaluation_scope"),
        "agent": candidate.get("agent"),
        "variant": candidate.get("variant"),
    }
    if any(value is None for value in identity.values()):
        return None
    return identity


def _validate_round(store: EvidenceStore, report_path: Path, record: Any, expected_round: int) -> None:
    label = f"router.c2rust_repair.rounds[{expected_round - 1}]"
    if not isinstance(record, dict) or record.get("round") != expected_round:
        fail("c2rust_repair_round_sequence", "repair rounds must be sequential", path=label)
    if record.get("semantic_pass") is True:
        fail("c2rust_repair_false_semantic_pass", "repair round cannot claim semantic pass", path=label)
    bindings = record.get("bindings")
    if not isinstance(bindings, dict):
        fail("c2rust_repair_round_bindings", "repair round bindings are missing", path=label)
    for key in REQUIRED_ROUND_BINDINGS:
        _validate_same_directory_ref(store, bindings.get(key), report_path.parent, f"{label}.{key}")
    for key in OPTIONAL_ROUND_BINDINGS:
        if bindings.get(key) is not None:
            _validate_same_directory_ref(store, bindings.get(key), report_path.parent, f"{label}.{key}")


def _validate_report_final_candidate(
    store: EvidenceStore,
    report_path: Path,
    report: dict[str, Any],
    expected_sha: str,
) -> None:
    final = report.get("final_candidate")
    if isinstance(final, dict) and final.get("path") is not None:
        actual = _validate_same_directory_ref(store, final, report_path.parent, "router.c2rust_repair.final")
    else:
        rounds = report.get("rounds")
        latest = rounds[-1] if isinstance(rounds, list) and rounds else None
        bindings = latest.get("bindings") if isinstance(latest, dict) else None
        candidate = bindings.get("candidate") if isinstance(bindings, dict) else None
        actual = _validate_same_directory_ref(
            store,
            candidate,
            report_path.parent,
            "router.c2rust_repair.latest_candidate",
        )
        if not isinstance(final, dict) or final.get("sha256") != actual:
            fail("c2rust_repair_final_candidate_drift", "repair final SHA-only ref drifted", path="router")
    if actual != expected_sha:
        fail("c2rust_repair_final_candidate_drift", "repair report final SHA differs from router", path="router")


def _report_has_bound_candidate(report: dict[str, Any]) -> bool:
    final = report.get("final_candidate")
    if isinstance(final, dict) and final.get("path") is not None:
        return True
    rounds = report.get("rounds")
    if not isinstance(rounds, list):
        return False
    return any(
        isinstance(record, dict)
        and isinstance(record.get("bindings"), dict)
        and isinstance(record["bindings"].get("candidate"), dict)
        for record in rounds
    )


def _validate_same_directory_ref(store: EvidenceStore, ref: Any, directory: Path, label: str) -> str:
    if not isinstance(ref, dict):
        fail("c2rust_repair_reference", f"{label} must be SHA-bound", path=label)
    expected = require_sha(ref.get("sha256"), f"{label}.sha256")
    _require_same_directory_path(ref.get("path"), label)
    path = store.resolve(ref.get("path"), label, parent=directory)
    if path.parent != directory or sha256_file(path) != expected:
        fail("c2rust_repair_hash_drift", f"{label} path or SHA drifted", path=label)
    store.checked_artifacts += 1
    return expected


def _require_same_directory_path(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value or "\\" in value:
        fail("c2rust_repair_path_escape", f"{label}.path must be a local filename", path=label)
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
        fail("c2rust_repair_path_escape", f"{label}.path must be a local filename", path=label)


def _one_source(items: list[Any], source: str) -> dict[str, Any] | None:
    matches = [item for item in items if isinstance(item, dict) and item.get("source") == source]
    if len(matches) > 1:
        fail("c2rust_repair_candidate_ambiguous", "multiple repair records found", path="router")
    return matches[0] if matches else None
