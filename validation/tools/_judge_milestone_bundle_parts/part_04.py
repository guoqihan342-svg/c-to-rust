def manifest_identity(manifest: dict[str, Any]) -> str | None:
    path = manifest.get("path")
    if not isinstance(path, str) or not path:
        return None
    sha = manifest.get("sha256")
    return f"{path}@{sha}" if isinstance(sha, str) and sha else path


def sorted_int_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def blocked_repairs_source(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return empty_blocked_repairs_rollup()
    return {
        "status": value.get("status") if isinstance(value.get("status"), str) else "unknown",
        "blocked_repair_count": int_or_zero(value.get("blocked_repair_count")),
        "slice_count": int_or_zero(value.get("slice_count")),
        "human_action_required_count": int_or_zero(value.get("human_action_required_count")),
        "human_intervention_points": string_list(value.get("human_intervention_points")),
        "blocked_callees": string_list(value.get("blocked_callees")),
        "ir_feature_gap_kinds": int_count_map(value.get("ir_feature_gap_kinds")),
        "forbidden_change_counts": int_count_map(value.get("forbidden_change_counts")),
        "blocked_reason_counts": int_count_map(value.get("blocked_reason_counts")),
        "source_span_kind_counts": int_count_map(value.get("source_span_kind_counts")),
        "smallest_next_tests": object_list(value.get("smallest_next_tests")),
        "next_actions": object_list(value.get("next_actions")),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


def build_blocked_repairs_route_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    human_points: list[str] = []
    callees: list[str] = []
    status_counts: dict[str, int] = {}
    gap_kinds: dict[str, int] = {}
    forbidden_changes: dict[str, int] = {}
    blocked_reasons: dict[str, int] = {}
    source_span_kinds: dict[str, int] = {}
    smallest_tests: list[dict[str, Any]] = []
    next_actions: list[dict[str, Any]] = []
    blocked_repair_count = 0
    slice_count = 0
    human_action_required_count = 0
    for source in sources:
        blocked = source.get("blocked_repairs", {}) if isinstance(source.get("blocked_repairs"), dict) else {}
        blocked_repair_count += int_or_zero(blocked.get("blocked_repair_count"))
        slice_count += int_or_zero(blocked.get("slice_count"))
        human_action_required_count += int_or_zero(blocked.get("human_action_required_count"))
        increment_count(status_counts, blocked.get("status"))
        for point in string_list(blocked.get("human_intervention_points")):
            append_unique(human_points, point)
        for callee in string_list(blocked.get("blocked_callees")):
            append_unique(callees, callee)
        merge_int_counts(gap_kinds, blocked.get("ir_feature_gap_kinds"))
        merge_int_counts(forbidden_changes, blocked.get("forbidden_change_counts"))
        merge_int_counts(blocked_reasons, blocked.get("blocked_reason_counts"))
        merge_int_counts(source_span_kinds, blocked.get("source_span_kind_counts"))
        for test in object_list(blocked.get("smallest_next_tests")):
            append_unique_dict(smallest_tests, test)
        for action in object_list(blocked.get("next_actions")):
            enriched = dict(action)
            if isinstance(source.get("entrypoint_id"), str) and "entrypoint_id" not in enriched:
                enriched["entrypoint_id"] = source["entrypoint_id"]
            append_unique_dict(next_actions, enriched)
    return {
        "status": "observed" if blocked_repair_count else "none",
        "blocked_repair_count": blocked_repair_count,
        "slice_count": slice_count,
        "human_action_required_count": human_action_required_count,
        "status_counts": status_counts,
        "human_intervention_points": human_points,
        "blocked_callees": callees,
        "ir_feature_gap_kinds": gap_kinds,
        "forbidden_change_counts": forbidden_changes,
        "blocked_reason_counts": blocked_reasons,
        "source_span_kind_counts": source_span_kinds,
        "smallest_next_tests": smallest_tests,
        "next_actions": next_actions,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "boundary": (
            "Blocked repairs summarize route-governance self-healing refusals only. They are not semantic "
            "acceptance and do not increase translator-generated coverage."
        ),
    }


def empty_blocked_repairs_rollup() -> dict[str, Any]:
    return {
        "status": "none",
        "blocked_repair_count": 0,
        "slice_count": 0,
        "human_action_required_count": 0,
        "status_counts": {},
        "human_intervention_points": [],
        "blocked_callees": [],
        "ir_feature_gap_kinds": {},
        "forbidden_change_counts": {},
        "blocked_reason_counts": {},
        "source_span_kind_counts": {},
        "smallest_next_tests": [],
        "next_actions": [],
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


def build_evidence_cost_retention_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    retention_classes: dict[str, dict[str, int]] = {}
    for source in sources:
        classes = source.get("retention_classes", {})
        if not isinstance(classes, dict):
            continue
        for class_name, counts in classes.items():
            if not isinstance(counts, dict):
                continue
            target = retention_classes.setdefault(str(class_name), {"file_count": 0, "total_bytes": 0})
            target["file_count"] += int_or_zero(counts.get("file_count"))
            target["total_bytes"] += int_or_zero(counts.get("total_bytes"))
    policy_tier_counts: dict[str, int] = {}
    policy_failed_gate_counts: dict[str, int] = {}
    for source in sources:
        policy = source.get("policy_compliance") if isinstance(source.get("policy_compliance"), dict) else {}
        tier = str(policy.get("policy_tier", "unknown"))
        policy_tier_counts[tier] = policy_tier_counts.get(tier, 0) + 1
        failed_gates = policy.get("failed_gates") if isinstance(policy.get("failed_gates"), list) else []
        for gate in failed_gates:
            gate_name = str(gate)
            policy_failed_gate_counts[gate_name] = policy_failed_gate_counts.get(gate_name, 0) + 1
    return {
        "report_kind": "evidence-cost-retention-rollup",
        "sources": sources,
        "rollup": {
            "source_count": len(sources),
            "artifact_count": sum(int_or_zero(source.get("artifact_count")) for source in sources),
            "total_bytes": sum(int_or_zero(source.get("total_bytes")) for source in sources),
            "pipeline_count": sum(int_or_zero(source.get("pipeline_count")) for source in sources),
            "runtime_ms": {
                "observation_count": sum(
                    int_or_zero(source.get("runtime_observation_count")) for source in sources
                ),
                "total": sum(int_or_zero(source.get("runtime_total_duration_ms")) for source in sources),
                "max": max(
                    [int_or_zero(source.get("runtime_max_duration_ms")) for source in sources],
                    default=0,
                ),
            },
            "retention_classes": retention_classes,
            "all_sources_passed": all(source.get("status") == "passed" for source in sources) if sources else True,
            "policy_compliance": {
                "all_sources_policy_passed": all(
                    isinstance(source.get("policy_compliance"), dict)
                    and source["policy_compliance"].get("status") == "passed"
                    for source in sources
                )
                if sources
                else True,
                "tier_counts": {key: policy_tier_counts[key] for key in sorted(policy_tier_counts)},
                "failed_gate_counts": {
                    key: policy_failed_gate_counts[key] for key in sorted(policy_failed_gate_counts)
                },
            },
            "portability_issue_count": sum(
                int_or_zero(source.get("claim_anchor_issue_count"))
                + int_or_zero(source.get("profile_hash_issue_count"))
                for source in sources
            ),
            "diagnostic_host_metadata_count": sum(
                int_or_zero(source.get("diagnostic_host_metadata_count")) for source in sources
            ),
        },
        "boundary": (
            "Evidence cost and retention metrics summarize artifact volume, runtime observations, and retention "
            "classes for review. They are not semantic acceptance evidence and do not increase translation coverage."
        ),
    }


def build_opencode_runtime_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "report_kind": "opencode-runtime-rollup",
        "sources": sources,
        "enabled_entrypoint_count": len(sources),
        "worker_count": sum(int_or_zero(source.get("worker_count")) for source in sources),
        "all_contracts_executed": bool(sources) and all(bool(source.get("all_contracts_executed")) for source in sources),
        "chat_output_is_evidence_false": all(source.get("chat_output_is_evidence") is False for source in sources),
        "semantic_gate_false": all(source.get("semantic_gate") is False for source in sources),
        "preflight_proof_summary": build_opencode_preflight_proof_rollup(sources),
    }


def build_opencode_preflight_proof_rollup(sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not sources:
        return opencode_preflight_absent_summary(required=False)
    summaries = [
        source.get("preflight_proof_summary")
        for source in sources
        if isinstance(source.get("preflight_proof_summary"), dict)
    ]
    passed = [summary for summary in summaries if summary.get("status") == "passed"]
    selected = deepcopy(passed[0] if passed else summaries[0]) if summaries else opencode_preflight_absent_summary(required=True)
    selected["required_when_opencode_runtime_enabled"] = True
    selected["source_count"] = len(sources)
    selected["passed_source_count"] = len(passed)
    if len(passed) != len(sources):
        selected["status"] = "failed"
    return selected


def build_retention_policy() -> dict[str, Any]:
    return {
        "report_kind": "milestone-retention-policy",
        "bundle_role": "external-review-index",
        "target_artifacts": {
            "retention_class": "reproducible-local-output",
            "committed": False,
            "policy": "Regenerate from the judge entrypoint commands; bind by repo-relative path and sha256.",
        },
        "committed_manifests": {
            "retention_class": "release-evidence",
            "policy": "Use validation/evidence manifests and config/competition-env profiles as committed anchors.",
        },
        "claim_boundary": "Retention policy does not expand semantic acceptance or translation coverage.",
    }


def load_present_json_artifact(artifact: dict[str, Any] | None, *, repo_root: Path) -> dict[str, Any] | None:
    if not isinstance(artifact, dict) or artifact.get("status") != "present":
        return None
    path_text = artifact.get("path")
    if not isinstance(path_text, str):
        return None
    try:
        return validator.load_json(resolve_input_path(Path(path_text), repo_root=repo_root))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def artifact_ref(path: Path, *, repo_root: Path) -> dict[str, Any]:
    ref = {
        "path": validator.repo_relative(path, repo_root),
        "status": "present" if path.is_file() else "missing",
    }
    if path.is_file():
        ref["sha256"] = validator.sha256_file(path)
    return ref


def resolve_input_path(path: Path, *, repo_root: Path) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
        resolved.relative_to(repo_root)
        return resolved
    path_text = path.as_posix()
    validator.assert_repo_relative_posix(path_text)
    return validator.repo_path(path_text, repo_root=repo_root)


def resolve_output_path(path: Path, *, repo_root: Path) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
        resolved.relative_to(repo_root)
        return resolved
    path_text = path.as_posix()
    validator.assert_repo_relative_posix(path_text)
    return validator.repo_path(path_text, repo_root=repo_root)


def remove_stale_publication_siblings(out_path: Path) -> None:
    for filename in ("public-release-packet.json", "milestone-release-notes.md"):
        (out_path.parent / filename).unlink(missing_ok=True)


def normalize_retention_classes(value: dict[str, Any]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for class_name, counts in value.items():
        if not isinstance(counts, dict):
            continue
        result[str(class_name)] = {
            "file_count": int_or_zero(counts.get("file_count")),
            "total_bytes": int_or_zero(counts.get("total_bytes")),
        }
    return result


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def int_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int_or_zero(count) for key, count in value.items()}


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def merge_int_counts(target: dict[str, int], value: object) -> None:
    for key, count in int_count_map(value).items():
        target[key] = target.get(key, 0) + count


def increment_count(target: dict[str, int], value: object) -> None:
    if isinstance(value, str) and value:
        target[value] = target.get(value, 0) + 1


def append_unique(items: list[str], value: object) -> None:
    if isinstance(value, str) and value and value not in items:
        items.append(value)


def append_unique_dict(items: list[dict[str, Any]], value: dict[str, Any]) -> None:
    if value not in items:
        items.append(value)


def int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def number_or_zero(value: object) -> int | float:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return 0


def first_string_value(sources: list[dict[str, Any]], key: str) -> str | None:
    for source in sources:
        value = source.get(key)
        if isinstance(value, str):
            return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
