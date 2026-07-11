from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from validation.tools._ai_candidate_harness_parts.router import (
    ALLOWED_SOURCES,
    MAX_CANDIDATES,
    REQUIRED_GATES,
    build_selection_policy,
    recompute_router_metrics,
    selection_policy_sha256,
)


HashFile = Callable[[Path], str]
SOURCE_KEYS = ("opencode-ai", "typed-ir", "c2rust-repair", "c2rust-baseline")
SOURCE_EVIDENCE_KEYS = {
    "opencode-ai": "ai",
    "typed-ir": "typed_ir",
    "c2rust-repair": "c2rust_repair",
    "c2rust-baseline": "c2rust_baseline",
}


def empty_router_unit() -> dict[str, Any]:
    return {
        "status": "not_applicable",
        "auto_manifest_sha256": None,
        "router_sha256": None,
        "candidate_inputs": 0,
        "unique": 0,
        "deduplicated": 0,
        "selected_by_source": {source: 0 for source in SOURCE_KEYS},
        "deterministic_fallbacks": 0,
        "no_selection": 0,
        "selected_source": None,
        "selected_candidate_sha256": None,
    }


def recompute_fresh_router_unit(
    *,
    ai_manifest_path: Path,
    target_id: str,
    slice_id: str,
    repo_root: Path,
    hash_file: HashFile,
) -> tuple[dict[str, Any], list[str]]:
    result = empty_router_unit()
    reasons: list[str] = []
    auto_manifest_path = _auto_manifest_path(ai_manifest_path)
    if auto_manifest_path is None or not auto_manifest_path.is_file():
        return result, ["ai_auto_translation_manifest_missing"]
    result["auto_manifest_sha256"] = hash_file(auto_manifest_path)
    auto_manifest = _load_object(auto_manifest_path, "ai_auto_translation_manifest", reasons)
    if auto_manifest is None:
        return result, reasons
    if auto_manifest.get("target_id") != target_id or auto_manifest.get("slice_id") != slice_id:
        reasons.append("ai_auto_translation_manifest_identity_mismatch")

    binding = auto_manifest.get("ai_exact_validation")
    router_path = _load_bound_path(
        binding,
        owner_path=auto_manifest_path,
        repo_root=repo_root,
        hash_file=hash_file,
        label="ai_exact_validation",
        reasons=reasons,
    )
    if router_path is None:
        return result, sorted(set(reasons))
    result["router_sha256"] = hash_file(router_path)
    router = _load_object(router_path, "ai_router", reasons)
    if router is None:
        return result, sorted(set(reasons))

    _validate_router_contract(router, router_path=router_path, repo_root=repo_root, hash_file=hash_file, reasons=reasons)
    semantic_pass = router.get("semantic_pass") is True
    if not isinstance(binding, dict) or binding.get("status") != ("passed" if semantic_pass else "failed"):
        reasons.append("ai_exact_validation_status_drift")
    if not isinstance(binding, dict) or binding.get("semantic_pass") is not semantic_pass:
        reasons.append("ai_exact_validation_semantic_pass_drift")
    if reasons:
        return result, sorted(set(reasons))

    metrics = router["metrics"]
    selected_id = router.get("selected_candidate_id")
    selected = next(
        (item for item in router["candidate_set"] if item.get("candidate_id") == selected_id),
        None,
    )
    selected_source = selected.get("source") if isinstance(selected, dict) else None
    result.update(
        {
            "status": "verified",
            "candidate_inputs": metrics["candidate_inputs"],
            "unique": metrics["unique_candidates"],
            "deduplicated": metrics["deduplicated_candidates"],
            "selected_by_source": {
                source: int(selected_source == source) for source in SOURCE_KEYS
            },
            "deterministic_fallbacks": int(
                selected_source in {"typed-ir", "c2rust-repair", "c2rust-baseline"}
            ),
            "no_selection": int(selected_source is None),
            "selected_source": selected_source,
            "selected_candidate_sha256": (
                selected.get("artifact_sha256") if isinstance(selected, dict) else None
            ),
        }
    )
    return result, []


def router_totals(units: list[dict[str, Any]]) -> dict[str, Any]:
    router_units = [unit.get("router", empty_router_unit()) for unit in units]
    return {
        "candidate_inputs": sum(item["candidate_inputs"] for item in router_units),
        "unique": sum(item["unique"] for item in router_units),
        "deduplicated": sum(item["deduplicated"] for item in router_units),
        "selected_by_source": {
            source: sum(item["selected_by_source"][source] for item in router_units)
            for source in SOURCE_KEYS
        },
        "deterministic_fallbacks": sum(item["deterministic_fallbacks"] for item in router_units),
        "no_selection": sum(item["no_selection"] for item in router_units),
    }


def _validate_router_contract(
    router: dict[str, Any],
    *,
    router_path: Path,
    repo_root: Path,
    hash_file: HashFile,
    reasons: list[str],
) -> None:
    if router.get("schema_version") != 1:
        reasons.append("ai_router_schema_version_invalid")
    policy = router.get("selection_policy")
    policy_hash = router.get("selection_policy_sha256")
    if not isinstance(policy, dict) or policy.get("full_router") is not True:
        reasons.append("ai_router_selection_policy_invalid")
    else:
        if policy_hash != selection_policy_sha256(policy):
            reasons.append("ai_router_selection_policy_sha256_drift")
        if policy.get("required_gates") != list(REQUIRED_GATES):
            reasons.append("ai_router_required_gates_drift")
        budget = policy.get("provider_invocation_budget")
        effective = budget.get("effective") if isinstance(budget, dict) else None
        if not isinstance(effective, int) or isinstance(effective, bool):
            reasons.append("ai_router_provider_budget_invalid")
        else:
            try:
                expected_policy = build_selection_policy(provider_invocation_budget=effective)
            except ValueError:
                reasons.append("ai_router_provider_budget_invalid")
            else:
                if policy != expected_policy:
                    reasons.append("ai_router_selection_policy_drift")
    candidates = router.get("candidate_set")
    duplicates = router.get("deduplicated_candidates")
    if not isinstance(candidates, list) or not isinstance(duplicates, list):
        reasons.append("ai_router_candidate_sets_invalid")
        return
    if len(candidates) + len(duplicates) > MAX_CANDIDATES:
        reasons.append("ai_router_candidate_limit_exceeded")
    try:
        expected_metrics = recompute_router_metrics(router)
    except (KeyError, TypeError, ValueError):
        reasons.append("ai_router_metrics_not_recomputable")
    else:
        if router.get("metrics") != expected_metrics:
            reasons.append("ai_router_metrics_drift")

    ids = [item.get("candidate_id") for item in candidates if isinstance(item, dict)]
    if len(ids) != len(candidates) or not all(isinstance(value, str) and value for value in ids) or len(set(ids)) != len(ids):
        reasons.append("ai_router_candidate_ids_invalid")
        return
    sources = [item.get("source") for item in candidates]
    if len(set(sources)) != len(sources):
        reasons.append("ai_router_unique_candidate_sources_duplicated")
    selected_id = router.get("selected_candidate_id")
    selected = [item for item in candidates if item.get("candidate_id") == selected_id]
    decisions = [item for item in candidates if item.get("decision") == "selected"]
    eligible = [item for item in candidates if item.get("decision") == "eligible_not_selected"]
    if selected_id is None:
        if decisions or eligible or router.get("semantic_pass") is not False:
            reasons.append("ai_router_no_selection_contract_invalid")
    elif len(selected) != 1 or decisions != selected or router.get("semantic_pass") is not True:
        reasons.append("ai_router_selection_contract_invalid")

    unique_by_id = {item["candidate_id"]: item for item in candidates}
    duplicate_ids: set[str] = set()
    for duplicate in duplicates:
        if not isinstance(duplicate, dict):
            reasons.append("ai_router_duplicate_record_invalid")
            continue
        duplicate_id = duplicate.get("candidate_id")
        original = unique_by_id.get(duplicate.get("duplicate_of"))
        facts = duplicate.get("rejection_facts")
        if (
            not isinstance(duplicate_id, str)
            or not duplicate_id
            or duplicate_id in unique_by_id
            or duplicate_id in duplicate_ids
            or not isinstance(original, dict)
            or duplicate.get("artifact_sha256") != original.get("artifact_sha256")
            or duplicate.get("source") not in ALLOWED_SOURCES
            or not isinstance(facts, list)
            or not facts
        ):
            reasons.append("ai_router_duplicate_record_invalid")
        duplicate_ids.add(duplicate_id)

    evidence = router.get("candidate_evidence")
    if not isinstance(evidence, dict):
        reasons.append("ai_router_candidate_evidence_missing")
        return
    for candidate in candidates:
        source = candidate.get("source")
        artifact_sha = candidate.get("artifact_sha256")
        if source not in ALLOWED_SOURCES or not _is_sha256(artifact_sha):
            reasons.append("ai_router_candidate_source_or_sha_invalid")
            continue
        accepted = candidate.get("accepted_gates")
        rejection_facts = candidate.get("rejection_facts")
        decision = candidate.get("decision")
        if candidate.get("schedule_index") != candidates.index(candidate):
            reasons.append("ai_router_schedule_index_drift")
        if decision not in {"selected", "eligible_not_selected", "rejected"}:
            reasons.append("ai_router_candidate_decision_invalid")
        if decision == "rejected" and (not isinstance(rejection_facts, list) or not rejection_facts):
            reasons.append("ai_router_rejection_facts_missing")
        if candidate.get("decision") == "selected" and (
            accepted != list(REQUIRED_GATES) or rejection_facts != []
        ):
            reasons.append("ai_router_selected_candidate_gate_contract_invalid")
        evidence_path = _load_bound_path(
            evidence.get(SOURCE_EVIDENCE_KEYS[source]),
            owner_path=router_path,
            repo_root=repo_root,
            hash_file=hash_file,
            label=f"ai_router_candidate_evidence_{source}",
            reasons=reasons,
        )
        if evidence_path is None:
            continue
        payload = _load_object(evidence_path, f"ai_router_candidate_evidence_{source}", reasons)
        if payload is None:
            continue
        if payload.get("candidate_sha256") != artifact_sha:
            reasons.append(f"ai_router_candidate_evidence_{source}_sha_drift")
        expected_status = "passed" if candidate.get("decision") in {"selected", "eligible_not_selected"} else "failed"
        if payload.get("status") != expected_status or payload.get("semantic_pass") is (expected_status != "passed"):
            reasons.append(f"ai_router_candidate_evidence_{source}_status_drift")
    if selected:
        selected_sha = selected[0].get("artifact_sha256")
        if router.get("canonical_draft_sha256") != selected_sha:
            reasons.append("ai_router_canonical_draft_sha256_drift")


def _auto_manifest_path(ai_manifest_path: Path) -> Path | None:
    suffix = "-ai-candidate-manifest.json"
    if not ai_manifest_path.name.endswith(suffix):
        return None
    return ai_manifest_path.with_name(ai_manifest_path.name[: -len(suffix)] + "-auto-translation-manifest.json")


def _load_bound_path(
    binding: Any,
    *,
    owner_path: Path,
    repo_root: Path,
    hash_file: HashFile,
    label: str,
    reasons: list[str],
) -> Path | None:
    if not isinstance(binding, dict):
        reasons.append(f"{label}_binding_missing")
        return None
    path_ref = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(path_ref, str) or not _is_safe_relative_path(path_ref) or not _is_sha256(expected_sha):
        reasons.append(f"{label}_binding_invalid")
        return None
    candidates = (owner_path.parent / path_ref, repo_root / path_ref)
    for candidate in candidates:
        resolved = candidate.resolve()
        if candidate.is_file() and (_within(resolved, owner_path.parent.resolve()) or _within(resolved, repo_root.resolve())):
            if hash_file(candidate) != expected_sha:
                reasons.append(f"{label}_sha256_drift")
                return None
            return candidate
    reasons.append(f"{label}_artifact_missing")
    return None


def _load_object(path: Path, label: str, reasons: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        reasons.append(f"{label}_invalid_json")
        return None
    if not isinstance(value, dict):
        reasons.append(f"{label}_not_object")
        return None
    return value


def _is_safe_relative_path(value: str) -> bool:
    if not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)
