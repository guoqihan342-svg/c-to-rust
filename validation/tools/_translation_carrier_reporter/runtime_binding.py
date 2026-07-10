from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .contract import ReporterError, behavior_fields, require_dict
from .source_binding import (
    StaticContext,
    file_ref,
    load_json,
    sha256_file,
    sha256_lf_stable_text_file,
)


HOST_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/]|/(?:tmp|mnt|home|root|Users?)/|\\\\wsl(?:\$|\.localhost)[\\/])",
    re.IGNORECASE,
)

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


def load_runtime_provenance(
    context: StaticContext,
    auto_evidence_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    auto_dir = auto_evidence_dir.resolve(strict=True)
    ensure_inside_repo(context, auto_dir, "auto evidence directory")
    slice_id = str(context.spec["slice_id"])
    prefix = f"l3-{slice_id}"
    paths = {
        "translator_input": auto_dir / f"{prefix}-translator-input.json",
        "translation_plan": auto_dir / f"{prefix}-auto-translation-plan.json",
        "clang_lowering_report": auto_dir / f"{prefix}-clang-lowering-report.json",
        "c_oracle_status": auto_dir / f"{prefix}-c-oracle-status.json",
        "c_oracle_harness": auto_dir / f"{prefix}-c-oracle-harness-draft.c",
        "rust_draft": auto_dir / f"{prefix}-rust-draft.rs",
        "rust_check": auto_dir / "rust-check.json",
        "test_translation": auto_dir / f"{prefix}-test-translation-generated.json",
        "candidate_rust_report": auto_dir / f"{prefix}-rust-report.json",
    }
    required_paths = (
        "translator_input",
        "translation_plan",
        "clang_lowering_report",
        "c_oracle_status",
        "c_oracle_harness",
        "rust_draft",
        "rust_check",
    )
    for label in required_paths:
        path = paths[label]
        if not path.is_file():
            raise ReporterError(f"required runtime artifact is missing: {label}")
    if not paths["test_translation"].is_file() and not paths["candidate_rust_report"].is_file():
        raise ReporterError("generated Rust replay evidence is missing")

    translator_input = load_json(paths["translator_input"])
    plan = load_json(paths["translation_plan"])
    lowering = load_json(paths["clang_lowering_report"])
    status = load_json(paths["c_oracle_status"])
    carrier = context.spec["translation_carrier"]
    fixture_hash = context.spec["fixture_hash"]
    for label, artifact in (
        ("translator input", translator_input),
        ("translation plan", plan),
        ("clang lowering report", lowering),
    ):
        if artifact.get("translation_carrier") != carrier:
            raise ReporterError(f"translation carrier binding drifted in {label}")
        for identity_key in ("target_id", "slice_id", "source_commit"):
            if artifact.get(identity_key) != context.spec.get(identity_key):
                raise ReporterError(f"{identity_key} drifted in {label}")
    if translator_input.get("fixture_hash") != fixture_hash:
        raise ReporterError("fixture hash drifted in translator input")
    if lowering.get("fixture_hash") != fixture_hash:
        raise ReporterError("fixture hash drifted in clang lowering report")
    fixture_cache_key = f"fixture_hash={fixture_hash}"
    if plan.get("fixture_hash") != fixture_hash and fixture_cache_key not in plan.get(
        "cache_invalidation_keys", []
    ):
        raise ReporterError("fixture hash drifted in translation plan")
    if translator_input.get("c_source") != context.spec.get("c_source"):
        raise ReporterError("carrier source drifted in translator input")
    if translator_input.get("function_name") != context.spec.get("function_name"):
        raise ReporterError("carrier function drifted in translator input")
    if translator_input.get("source_root") != context.spec.get("source_root"):
        raise ReporterError("source_root drifted in translator input")
    if translator_input.get("source_file") != context.spec.get("source_file"):
        raise ReporterError("source_file drifted in translator input")
    artifact_source_hashes = {
        str(context.spec["source_file"]): sha256_lf_stable_text_file(context.source_path)
    }
    if translator_input.get("source_file_hashes") != artifact_source_hashes:
        raise ReporterError("source file hashes drifted in translator input")
    if require_dict(translator_input.get("build_profile"), "translator build_profile").get("clang_ast_fixture"):
        raise ReporterError("live carrier input must not use a clang AST fixture")
    if plan.get("status") not in {"generated", "draft_generated"}:
        raise ReporterError("translation plan is not generated")
    if plan.get("translation_source", {}).get("selected") != "clang-lowered-typed-ir":
        raise ReporterError("translation plan did not select clang-lowered typed IR")
    if lowering.get("status") != "lowered":
        raise ReporterError("clang lowering report is not lowered")
    if lowering.get("function_name") != context.spec.get("function_name"):
        raise ReporterError("lowered function does not match carrier function")
    if lowering.get("lowering_report", {}).get("frontend") != "clang_slice_source":
        raise ReporterError("carrier lowering did not use clang_slice_source")
    if lowering.get("metadata", {}).get("clang_ast_fixture"):
        raise ReporterError("carrier lowering report binds a forbidden AST fixture")
    metadata = lowering.get("metadata", {})
    if metadata.get("source_root") != context.spec.get("source_root"):
        raise ReporterError("source_root drifted in clang lowering report")
    if metadata.get("logical_source_file") != context.spec.get("source_file"):
        raise ReporterError("source_file drifted in clang lowering report")
    if metadata.get("source_file_hashes") != artifact_source_hashes:
        raise ReporterError("source file hashes drifted in clang lowering report")
    candidate = lowering.get("typed_ir_candidate", {})
    if (
        candidate.get("status") != "generated"
        or candidate.get("rust_draft_generated") is not True
        or candidate.get("semantic_pass") is not False
    ):
        raise ReporterError("typed-IR candidate binding is incomplete")

    validate_status_identity(context, status)
    harness_path = resolve_status_path(context, status, "/harness_draft_ref/path")
    if harness_path != paths["c_oracle_harness"].resolve():
        raise ReporterError("C oracle status points to an unexpected harness draft")
    harness_sha = sha256_file(harness_path)
    if json_pointer(status, "/harness_draft_ref/sha256") != harness_sha:
        raise ReporterError("C oracle harness hash drifted")
    validate_harness(context, harness_path, status)
    proof = validate_execution_or_promotion(context, status, output_dir, prefix)
    generated_replay = validate_generated_rust_replay(context, paths, lowering)
    generated_runtime_paths = generated_replay.pop("runtime_paths")

    return {
        "binding_mode": proof["binding_mode"],
        "compile_execution": proof.get("compile_execution"),
        "generated_rust_replay": generated_replay,
        "generated_rust_paths": generated_runtime_paths,
        "refs": {
            **context.refs,
            "translator_input": file_ref(context.repo_root, paths["translator_input"]),
            "translation_plan": field_bound_ref(
                context.repo_root,
                paths["translation_plan"],
                status=plan.get("status"),
            ),
            "clang_lowering_report": field_bound_ref(
                context.repo_root,
                paths["clang_lowering_report"],
                status=lowering.get("status"),
            ),
            "c_oracle_status": field_bound_ref(
                context.repo_root,
                paths["c_oracle_status"],
                status=status.get("status"),
                semantic_pass=status.get("semantic_pass"),
            ),
            "c_oracle_harness": file_ref(context.repo_root, harness_path),
            **generated_replay["refs"],
        },
    }


def validate_generated_rust_replay(
    context: StaticContext,
    paths: dict[str, Path],
    lowering: dict[str, Any],
) -> dict[str, Any]:
    for label in ("rust_draft", "rust_check"):
        if not paths[label].is_file():
            raise ReporterError(f"required generated Rust artifact is missing: {label}")
    draft_path = paths["rust_draft"].resolve()
    draft_sha = sha256_file(draft_path)
    if lowering.get("typed_ir_candidate", {}).get("rust_draft_sha256") != draft_sha:
        raise ReporterError("generated Rust draft hash does not match lowering report")

    rust_check = load_json(paths["rust_check"])
    validate_rust_check(context, rust_check)
    candidate_report = (
        load_json(paths["candidate_rust_report"])
        if paths["candidate_rust_report"].is_file()
        else None
    )
    if candidate_report is not None:
        validate_candidate_rust_report(context, candidate_report, draft_path, draft_sha)

    test_translation = (
        load_json(paths["test_translation"])
        if paths["test_translation"].is_file()
        else None
    )
    replay_source_artifact = test_translation
    replay = test_translation
    replay_source_path = paths["test_translation"]
    if replay is None and candidate_report is not None:
        replay = candidate_report.get("replay")
        replay_source_artifact = candidate_report
        replay_source_path = paths["candidate_rust_report"]
    if not isinstance(replay, dict):
        raise ReporterError("generated Rust replay evidence is missing")
    if not isinstance(replay_source_artifact, dict):
        raise ReporterError("generated Rust replay source artifact is missing")
    validate_replay_payload(context, replay)

    replay_test_path, replay_test_sha = validate_replay_test_ref(context, replay)
    execution = require_dict(replay.get("replay_execution"), "generated replay execution")
    stdout_path = resolve_repo_path(context, execution.get("stdout_log"), "replay stdout log")
    stderr_path = resolve_repo_path(context, execution.get("stderr_log"), "replay stderr log")
    for label, path in (("replay stdout log", stdout_path), ("replay stderr log", stderr_path)):
        if not path.is_file():
            raise ReporterError(f"{label} is missing")

    refs = {
        "generated_rust_draft": file_ref(context.repo_root, draft_path),
        "rust_check": field_bound_ref(
            context.repo_root,
            paths["rust_check"],
            status=rust_check.get("status"),
        ),
        "generated_replay_evidence": replay_artifact_ref(
            context.repo_root,
            replay_source_path,
            replay_source_artifact,
        ),
        "generated_replay_test": {
            **file_ref(context.repo_root, replay_test_path),
            "declared_sha256": replay_test_sha,
        },
        "generated_replay_stdout": file_ref(context.repo_root, stdout_path),
        "generated_replay_stderr": file_ref(context.repo_root, stderr_path),
    }
    if candidate_report is not None:
        refs["candidate_rust_report"] = replay_artifact_ref(
            context.repo_root,
            paths["candidate_rust_report"],
            candidate_report,
        )
    if test_translation is not None:
        refs["test_translation"] = replay_artifact_ref(
            context.repo_root,
            paths["test_translation"],
            test_translation,
        )
    return {
        "status": "passed",
        "generated_draft_replay_pass": True,
        "generated_draft_semantic_pass": False,
        "fixture_external_stub": replay["fixture_external_stub"],
        "replay_execution": execution,
        "refs": refs,
        "runtime_paths": {
            "draft": draft_path,
            "replay_test": replay_test_path,
        },
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
    if harness.get("status") != "emitted" or harness.get("semantics_verified") is not False:
        raise ReporterError("rust-check fixture-only semantics boundary drifted")
    bindings = harness.get("bindings")
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
    stub = require_dict(replay.get("fixture_external_stub"), "fixture_external_stub")
    if (
        stub.get("kind") != context.contract["kind"]
        or stub.get("scope") != "fixture_only"
        or stub.get("semantics_verified") is not False
    ):
        raise ReporterError("generated replay external stub semantics boundary drifted")
    execution = require_dict(replay.get("replay_execution"), "generated replay execution")
    if (
        execution.get("status") != "passed"
        or execution.get("compile_returncode") != 0
        or execution.get("run_returncode") != 0
    ):
        raise ReporterError("generated replay compile or run did not pass")
    reject_host_path_text(execution.get("compile_command"), "generated replay compile command")
    reject_host_path_text(execution.get("run_command"), "generated replay run command")
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


def resolve_repo_path(context: StaticContext, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ReporterError(f"{label} path is missing")
    path = Path(value)
    resolved = (path if path.is_absolute() else context.repo_root / path).resolve(strict=True)
    ensure_inside_repo(context, resolved, label)
    return resolved


def validate_status_identity(context: StaticContext, status: dict[str, Any]) -> None:
    for key in ("target_id", "slice_id"):
        if status.get(key) != context.spec.get(key):
            raise ReporterError(f"C oracle status {key} drifted")
    if status.get("source_commit") not in (None, context.spec.get("source_commit")):
        raise ReporterError("C oracle status source_commit drifted")
    if status.get("fixture") != context.fixture_path.relative_to(context.repo_root).as_posix():
        raise ReporterError("C oracle status fixture path drifted")
    status_fixture_sha = status.get("fixture_sha256")
    if status_fixture_sha is not None and status_fixture_sha != context.spec.get("fixture_hash"):
        raise ReporterError("C oracle status fixture hash drifted")


def validate_harness(
    context: StaticContext,
    harness_path: Path,
    status: dict[str, Any],
) -> None:
    harness = harness_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    c_source = str(context.spec["c_source"]).replace("\r\n", "\n").replace("\r", "\n")
    if harness.count(c_source) != 1:
        raise ReporterError("C oracle harness must embed the carrier source exactly once")
    markers = expected_markers(context)
    missing_from_source = [marker for marker in markers if marker not in harness]
    if missing_from_source:
        raise ReporterError("C oracle harness does not assert every fixture output field")
    output_gate = status.get("compile_execution", {}).get("harness_execution", {}).get("output_gate", {})
    if output_gate:
        matched = output_gate.get("matched_stdout_fragments")
        if not isinstance(matched, list) or any(marker not in matched for marker in markers):
            raise ReporterError("C oracle harness output gate did not match every fixture field")


def validate_execution_or_promotion(
    context: StaticContext,
    status: dict[str, Any],
    output_dir: Path,
    prefix: str,
) -> dict[str, Any]:
    compile_execution = status.get("compile_execution")
    if isinstance(compile_execution, dict):
        execution = compile_execution.get("harness_execution")
        output_gate = execution.get("output_gate") if isinstance(execution, dict) else None
        if (
            compile_execution.get("status") != "compile_succeeded_not_oracle"
            or compile_execution.get("returncode") != 0
            or not isinstance(execution, dict)
            or execution.get("status") != "exited_zero_not_oracle"
            or execution.get("returncode") != 0
            or not isinstance(output_gate, dict)
            or output_gate.get("status") != "matched_not_oracle"
            or output_gate.get("missing_stdout_fragments") != []
        ):
            raise ReporterError("C oracle harness compile, execution, or output gate did not pass")
        return {
            "binding_mode": "executed_harness",
            "compile_execution": portable_compile_execution(compile_execution),
        }

    if status.get("status") != "C_ORACLE_GENERATED" or status.get("semantic_pass") is not True:
        raise ReporterError("C oracle status has neither executed harness proof nor accepted promotion")
    accepted = require_dict(status.get("accepted_oracle"), "accepted_oracle")
    expected = (output_dir / f"{prefix}-c-oracle.json").resolve()
    accepted_path = resolve_status_path(context, status, "/accepted_oracle/path")
    if accepted_path != expected or accepted.get("status") != "passed":
        raise ReporterError("promoted C oracle does not bind the expected accepted report")
    if not expected.is_file() or accepted.get("sha256") != sha256_file(expected):
        raise ReporterError("promoted accepted C oracle hash drifted")
    return {"binding_mode": "promoted_accepted_oracle"}


def expected_markers(context: StaticContext) -> list[str]:
    fields = behavior_fields(context.contract)
    return [f"fixture case {case['id']} {field} matched" for case in context.cases for field in fields]


def resolve_status_path(context: StaticContext, status: dict[str, Any], pointer: str) -> Path:
    value = json_pointer(status, pointer)
    if not isinstance(value, str) or not value:
        raise ReporterError(f"C oracle status is missing {pointer}")
    path = Path(value)
    resolved = (path if path.is_absolute() else context.repo_root / path).resolve(strict=True)
    ensure_inside_repo(context, resolved, pointer)
    return resolved


def json_pointer(value: dict[str, Any], pointer: str) -> Any:
    current: Any = value
    for token in pointer.strip("/").split("/"):
        if not isinstance(current, dict) or token not in current:
            raise ReporterError(f"missing JSON field: {pointer}")
        current = current[token]
    return current


def ensure_inside_repo(context: StaticContext, path: Path, label: str) -> None:
    try:
        path.relative_to(context.repo_root)
    except ValueError as exc:
        raise ReporterError(f"{label} escapes repo root") from exc


def reject_host_path_text(value: Any, label: str) -> None:
    if value is not None and (not isinstance(value, str) or HOST_PATH_PATTERN.search(value)):
        raise ReporterError(f"{label} contains a host-local absolute path")


def portable_compile_execution(execution: dict[str, Any]) -> dict[str, Any]:
    portable = copy.deepcopy(execution)
    logical_argv = portable.get("argv")
    if isinstance(logical_argv, list):
        portable["execution_argv"] = list(logical_argv)
    compiler_name = portable.get("compiler_name") or portable.get("requested_compiler")
    if isinstance(compiler_name, str) and compiler_name:
        portable["compiler_path"] = compiler_name
    harness = portable.get("harness_execution")
    if isinstance(harness, dict):
        harness_argv = harness.get("argv")
        if isinstance(harness_argv, list):
            harness["execution_argv"] = list(harness_argv)
        harness.pop("executable_path", None)
    portable["command_recording"] = "portable_logical_argv"
    return portable
