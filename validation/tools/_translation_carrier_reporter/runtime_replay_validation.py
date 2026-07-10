from __future__ import annotations

from pathlib import Path
from typing import Any

from .constant_state_contract import KIND as CONSTANT_STATE_KIND
from .contract import ReporterError, behavior_fields, require_dict
from .field_add_contract import KIND as FIELD_ADD_KIND
from .runtime_oracle_validation import reject_host_path_text, resolve_repo_path
from .source_binding import StaticContext, file_ref, sha256_file


MUTABLE_AUTO_ARTIFACT_CYCLE_BOUNDARY = (
    "Accepted-evidence promotion may rewrite this mutable auto artifact after reporter "
    "validation; this reference is field-bound rather than hash-bound to avoid cyclic or "
    "stale sha256 bindings."
)


def field_bound_ref(root: Path, path: Path, **fields: Any) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "binding_mode": "field_bound",
        **fields,
        "cycle_boundary": MUTABLE_AUTO_ARTIFACT_CYCLE_BOUNDARY,
    }


def replay_artifact_ref(
    root: Path,
    path: Path,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return field_bound_ref(
        root,
        path,
        status=artifact.get("status"),
        generated_draft_replay_pass=artifact.get("generated_draft_replay_pass"),
        generated_draft_semantic_pass=artifact.get("generated_draft_semantic_pass"),
    )


def validate_rust_check(context: StaticContext, rust_check: dict[str, Any]) -> None:
    if rust_check.get("status") != "passed":
        raise ReporterError("rust-check status is not passed")
    reject_host_path_text(rust_check.get("command"), "rust-check command")
    harness = require_dict(
        rust_check.get("rust_check_harness_only_bindings"),
        "rust-check harness-only bindings",
    )
    bindings = harness.get("bindings")
    if context.contract.get("kind") in {FIELD_ADD_KIND, CONSTANT_STATE_KIND}:
        if (
            harness.get("status") != "none"
            or harness.get("semantics_verified") is not False
            or bindings != []
        ):
            raise ReporterError("record field replay must not use external fixture bindings")
        external_context = require_dict(
            rust_check.get("external_callee_context"),
            "rust-check external callee context",
        )
        if (
            external_context.get("status") != "not_applicable"
            or external_context.get("declared_count") != 0
            or external_context.get("blocked_count") != 0
            or external_context.get("declared_callees") != []
        ):
            raise ReporterError("record field replay external callee context drifted")
        return
    if harness.get("status") != "emitted" or harness.get("semantics_verified") is not False:
        raise ReporterError("rust-check fixture-only semantics boundary drifted")
    if not isinstance(bindings, list) or not bindings:
        raise ReporterError("rust-check fixture-only binding is missing")
    expected_name = context.contract["external_callee"]["name"]
    matching = [item for item in bindings if isinstance(item, dict) and item.get("name") == expected_name]
    if len(matching) != 1:
        raise ReporterError("rust-check external fixture binding drifted")
    binding = matching[0]
    if (
        binding.get("fixture_only") is not True
        or binding.get("semantics_verified") is not False
        or binding.get("replay_contract_kind") != context.contract["kind"]
    ):
        raise ReporterError("rust-check external binding overclaims semantics")
    external_context = require_dict(
        rust_check.get("external_callee_context"),
        "rust-check external callee context",
    )
    declared = external_context.get("declared_callees")
    matching_declared = [
        item for item in declared or [] if isinstance(item, dict) and item.get("name") == expected_name
    ]
    if len(matching_declared) != 1 or matching_declared[0].get("semantics_verified") is not False:
        raise ReporterError("rust-check external callee context overclaims semantics")


def validate_candidate_rust_report(
    context: StaticContext,
    report: dict[str, Any],
    draft_path: Path,
    draft_sha: str,
) -> None:
    validate_identity(context, report, "candidate rust report", source_commit_optional=True)
    if (
        report.get("status") != "passed"
        or report.get("generated_draft_replay_pass") is not True
        or report.get("generated_draft_semantic_pass") is not False
    ):
        raise ReporterError("candidate rust report replay or semantic boundary drifted")
    draft_ref = require_dict(report.get("generated_draft"), "candidate generated_draft")
    declared_path = resolve_repo_path(context, draft_ref.get("path"), "candidate rust draft")
    if declared_path != draft_path or draft_ref.get("sha256") != draft_sha:
        raise ReporterError("candidate rust draft path or sha256 drifted")


def validate_replay_payload(context: StaticContext, replay: dict[str, Any]) -> None:
    validate_identity(context, replay, "generated replay", source_commit_optional=False)
    if (
        replay.get("status") != "passed"
        or replay.get("generated_draft_replay_pass") is not True
        or replay.get("generated_draft_semantic_pass") is not False
    ):
        raise ReporterError("generated draft replay did not pass or overclaims semantics")
    if replay.get("behavior_fields") != behavior_fields(context.contract):
        raise ReporterError("generated replay behavior fields drifted")
    if context.contract.get("kind") in {FIELD_ADD_KIND, CONSTANT_STATE_KIND}:
        model = require_dict(replay.get("fixture_state_model"), "fixture_state_model")
        expected_operation = (
            "constant_assign"
            if context.contract.get("kind") == CONSTANT_STATE_KIND
            else "wrapping_add"
        )
        if model.get("kind") != context.contract["kind"] or model.get("scope") != "fixture_only":
            raise ReporterError("generated replay state model boundary drifted")
        if model.get("operation") != expected_operation or replay.get("fixture_external_stub") is not None:
            raise ReporterError("generated replay state model boundary drifted")
        if context.contract.get("kind") == CONSTANT_STATE_KIND and model.get("value") != 0:
            raise ReporterError("generated replay constant-state value drifted")
        execution = require_dict(replay.get("replay_execution"), "generated replay execution")
        validate_replay_execution(execution)
        validate_replay_fixture_ref(context, replay)
        return
    stub = require_dict(replay.get("fixture_external_stub"), "fixture_external_stub")
    if (
        stub.get("kind") != context.contract["kind"]
        or stub.get("scope") != "fixture_only"
        or stub.get("semantics_verified") is not False
    ):
        raise ReporterError("generated replay external stub semantics boundary drifted")
    execution = require_dict(replay.get("replay_execution"), "generated replay execution")
    validate_replay_execution(execution)
    validate_replay_fixture_ref(context, replay)


def validate_replay_execution(execution: dict[str, Any]) -> None:
    if (
        execution.get("status") != "passed"
        or execution.get("compile_returncode") != 0
        or execution.get("run_returncode") != 0
    ):
        raise ReporterError("generated replay compile or run did not pass")
    reject_host_path_text(execution.get("compile_command"), "generated replay compile command")
    reject_host_path_text(execution.get("run_command"), "generated replay run command")


def validate_replay_fixture_ref(context: StaticContext, replay: dict[str, Any]) -> None:
    fixtures = replay.get("source_test_inputs", {}).get("fixtures")
    expected_fixture_path = context.fixture_path.relative_to(context.repo_root).as_posix()
    matching = [
        item
        for item in fixtures or []
        if isinstance(item, dict) and item.get("path") == expected_fixture_path
    ]
    if (
        len(matching) != 1
        or matching[0].get("hash") != context.spec.get("fixture_hash")
        or matching[0].get("operation_count") != len(context.cases)
    ):
        raise ReporterError("generated replay fixture binding drifted")


def validate_replay_test_ref(
    context: StaticContext,
    replay: dict[str, Any],
) -> tuple[Path, str]:
    test_draft_path = resolve_repo_path(context, replay.get("test_draft"), "replay test draft")
    tests = replay.get("rust_tests")
    if not isinstance(tests, list) or not tests:
        raise ReporterError("generated replay test ref is missing")
    matching = [
        item
        for item in tests
        if isinstance(item, dict)
        and resolve_repo_path(context, item.get("file"), "rust test file") == test_draft_path
    ]
    if len(matching) != 1:
        raise ReporterError("generated replay test path drifted")
    declared_sha = matching[0].get("file_hash")
    if not isinstance(declared_sha, str) or declared_sha != sha256_file(test_draft_path):
        raise ReporterError("generated replay test sha256 drifted")
    return test_draft_path, declared_sha


def validate_identity(
    context: StaticContext,
    artifact: dict[str, Any],
    label: str,
    *,
    source_commit_optional: bool,
) -> None:
    for key in ("target_id", "slice_id"):
        if artifact.get(key) != context.spec.get(key):
            raise ReporterError(f"{label} {key} drifted")
    source_commit = artifact.get("source_commit")
    if (not source_commit_optional or source_commit is not None) and source_commit != context.spec.get(
        "source_commit"
    ):
        raise ReporterError(f"{label} source_commit drifted")
