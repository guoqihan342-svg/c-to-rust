from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .contract import ReporterError, behavior_fields, require_dict
from .state_replay_kinds import is_state_replay_kind
from .source_binding import (
    StaticContext,
    file_ref,
    load_json,
    sha256_file,
    sha256_lf_stable_text_file,
)


from .runtime_replay_validation import (
    replay_artifact_ref,
    validate_candidate_rust_report,
    validate_replay_payload,
    validate_replay_test_ref,
    validate_rust_check,
)
from .runtime_oracle_validation import (
    ensure_inside_repo,
    json_pointer,
    resolve_repo_path,
    resolve_status_path,
    validate_execution_or_promotion,
    validate_harness,
    validate_status_identity,
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
    result = {
        "status": "passed",
        "generated_draft_replay_pass": True,
        "generated_draft_semantic_pass": False,
        "replay_execution": execution,
        "refs": refs,
        "runtime_paths": {
            "draft": draft_path,
            "replay_test": replay_test_path,
        },
    }
    if is_state_replay_kind(context.contract):
        result["fixture_state_model"] = replay["fixture_state_model"]
    else:
        result["fixture_external_stub"] = replay["fixture_external_stub"]
    return result
