from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
import re
from typing import Any

from .context import canonical_json_bytes
from .context_security import redact_metadata_text, resolve_under, sanitize_value, sha256_path
from .context_source import bytes_hash_match_mode, path_hash_match_mode
from .source_span_binding import extract_strict_span


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_FAILURES = 24
MAX_MESSAGE_BYTES = 512
MAX_DETAILS_BYTES = 1_024
MAX_SOURCE_FILES = 64
MAX_ARGV_ITEMS = 256
MAX_SPAN_BYTES = 1_048_576


def prove_fresh_oracle(
    spec: Mapping[str, Any] | Any,
    oracle_payload: Mapping[str, Any] | Any,
    harness_path: str | Path,
    source_root: str | Path | None = None,
    *,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Prove one freshly generated C harness run without trusting old evidence.

    Historical oracle, Rust, diff, and final-verification references in the
    slice spec are deliberately outside this function's input identity.
    """
    failures: list[dict[str, Any]] = []
    if not isinstance(spec, Mapping) or not isinstance(oracle_payload, Mapping):
        return _result({}, [_failure("malformed_input", "Spec and oracle payload must be objects.")])

    root = Path(source_root or Path.cwd()).resolve()
    artifact_base = Path(artifact_root or root).resolve()
    harness = _safe_path(artifact_base, harness_path, "harness", failures)
    harness_sha = _file_sha(harness, "harness", failures)
    harness_ref = oracle_payload.get("harness_draft_ref")
    if not isinstance(harness_ref, Mapping):
        failures.append(_failure("harness_binding_missing", "Fresh harness reference is missing."))
    else:
        _verify_ref(artifact_base, harness_ref, harness, harness_sha, "harness", failures)

    if oracle_payload.get("status") != "DRAFT_GENERATED" or oracle_payload.get("semantic_pass") is not False:
        failures.append(
            _failure(
                "not_fresh_generation",
                "Oracle payload must be a non-semantic DRAFT_GENERATED result from this run.",
            )
        )
    if "accepted_oracle" in oracle_payload:
        failures.append(_failure("historical_evidence_present", "Fresh oracle payload contains accepted evidence."))

    fixture_path, fixture_sha = _fixture_binding(spec, oracle_payload, root, failures)
    fixture_identity, observable_outputs = _fixture_outputs(
        oracle_payload,
        fixture_sha,
        failures,
    )
    source_bindings, span_binding = _source_bindings(spec, oracle_payload, root, failures)
    compile_binding = _compile_binding(spec, oracle_payload, harness, artifact_base, failures)
    build_profile = spec.get("build_profile")
    if not isinstance(build_profile, Mapping):
        failures.append(_failure("build_profile_missing", "Build profile identity is missing."))
        build_profile = {}
    target_contract = _target_contract(build_profile)
    abi = {
        "target": build_profile.get("target"),
        "target_abi_contract": _mapping(spec.get("c_boundary")).get("target_abi_contract"),
        "normalized_target_contract": target_contract,
    }
    if not target_contract:
        failures.append(_failure("abi_identity_missing", "Target ABI identity is missing."))

    source_identity = _hash_json({"files": source_bindings, "span": span_binding})
    fixture_content_sha = fixture_sha if _valid_sha(fixture_sha) else _hash_json({"status": "invalid"})
    flags_identity = _hash_json(compile_binding.get("flags", {}))
    abi_identity = _hash_json(abi)
    reuse_identity = {
        "source_sha256": source_identity,
        "fixture_sha256": fixture_content_sha,
        "flags_sha256": flags_identity,
        "abi_sha256": abi_identity,
    }
    build_profile_identity = _hash_json(build_profile)
    run_identity = {
        "reuse_key_sha256": _hash_json(reuse_identity),
        "harness_sha256": harness_sha,
        "compile_command_sha256": compile_binding.get("compile_command_sha256"),
        "compile_execution_sha256": compile_binding.get("compile_execution_sha256"),
        "build_profile_sha256": build_profile_identity,
    }
    bindings = {
        "harness": {"sha256": harness_sha, "path": _logical(artifact_base, harness)},
        "fixture": {"sha256": fixture_sha, "path": _logical(root, fixture_path)},
        "source_files": source_bindings,
        "source_span": span_binding,
        "build_profile_sha256": build_profile_identity,
        "abi_sha256": abi_identity,
        "flags_sha256": flags_identity,
        "reuse_key_sha256": run_identity["reuse_key_sha256"],
    }
    proof = {
        "shared_fixture_identity": fixture_identity,
        "observable_outputs": observable_outputs,
        "target_contract": target_contract,
        "target_contract_sha256": _hash_json(target_contract),
    }
    return _result({"run": run_identity, "bindings": bindings, "proof": proof}, failures)


def _fixture_binding(
    spec: Mapping[str, Any], payload: Mapping[str, Any], root: Path, failures: list[dict[str, Any]]
) -> tuple[Path | None, str | None]:
    fixture = _mapping(spec.get("fixture_contract"))
    raw_path = fixture.get("path") or fixture.get("input")
    expected_sha = fixture.get("sha256")
    path = _safe_path(root, raw_path, "fixture", failures)
    actual_sha = _file_sha(path, "fixture", failures)
    if expected_sha is not None and not _valid_sha(expected_sha):
        failures.append(_failure("fixture_hash_invalid", "Explicit fixture SHA-256 binding is invalid."))
    elif _valid_sha(expected_sha) and actual_sha != str(expected_sha).lower():
        failures.append(_failure("fixture_hash_mismatch", "Fixture SHA-256 drifted."))
    declared = payload.get("fixture")
    binding_path = _mapping(payload.get("fixture_binding")).get("path")
    for value in (declared, binding_path):
        if value is None:
            failures.append(_failure("fixture_binding_missing", "Fresh run fixture path is missing."))
        elif _safe_path(root, value, "fixture binding", failures) != path:
            failures.append(_failure("fixture_path_mismatch", "Fresh run used a different fixture path."))
    return path, actual_sha


def _fixture_outputs(
    payload: Mapping[str, Any],
    fixture_sha: str | None,
    failures: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = _mapping(payload.get("fixture_binding"))
    fields = binding.get("behavior_fields")
    cases = binding.get("case_bindings")
    if not isinstance(fields, list) or not fields or not all(isinstance(item, str) for item in fields):
        failures.append(_failure("observable_fields_missing", "Fixture observable outputs are missing."))
        fields = []
    if not isinstance(cases, list) or not cases:
        failures.append(_failure("fixture_cases_missing", "Fresh oracle fixture cases are missing."))
        cases = []
    identity_cases: list[dict[str, Any]] = []
    outputs: dict[str, Any] = {}
    for case in cases:
        if not isinstance(case, Mapping):
            failures.append(_failure("fixture_case_invalid", "Fresh oracle fixture case is invalid."))
            continue
        case_id = case.get("id")
        expected = case.get("expected_outputs")
        if not isinstance(case_id, str) or not case_id or not isinstance(expected, Mapping):
            failures.append(_failure("fixture_case_invalid", "Fresh oracle fixture case is incomplete."))
            continue
        if case.get("missing_observable_outputs"):
            failures.append(_failure("fixture_outputs_incomplete", "Fixture case misses observable outputs."))
            continue
        identity_cases.append({"id": case_id, "input_binding": case.get("input_ref")})
        outputs[case_id] = sanitize_value(dict(expected))
    identity = {
        "fixture_sha256": fixture_sha,
        "behavior_fields": list(fields),
        "cases": identity_cases,
    }
    return identity, outputs


def _target_contract(build_profile: Mapping[str, Any]) -> dict[str, Any]:
    target = _mapping(build_profile.get("target"))
    triple = target.get("triple_or_abi") or build_profile.get("target_triple") or build_profile.get("abi")
    pointer_width = target.get("pointer_width")
    endianness = target.get("endianness")
    if not isinstance(triple, str) or not triple.strip():
        return {}
    if pointer_width not in {16, 32, 64, 128} or endianness not in {"little", "big"}:
        return {}
    return {
        "schema_version": 1,
        "target_triple": triple,
        "pointer_width": pointer_width,
        "endianness": endianness,
        "calling_convention": str(target.get("calling_convention") or "C"),
    }


def _source_bindings(
    spec: Mapping[str, Any], payload: Mapping[str, Any], root: Path, failures: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = _mapping(spec.get("source"))
    source_root_value = spec.get("source_root") or source.get("source_root") or "."
    base = _safe_path(root, source_root_value, "declared source root", failures) or root
    hashes: dict[str, Any] = {}
    for raw in (source.get("source_file_hashes"), spec.get("source_file_hashes")):
        if isinstance(raw, Mapping):
            for key, value in raw.items():
                normalized_key = str(key)
                if normalized_key in hashes and hashes[normalized_key] != value:
                    failures.append(_failure("source_hash_conflict", "Source file has conflicting declared hashes."))
                hashes[normalized_key] = value
    if not hashes:
        failures.append(_failure("source_bindings_missing", "No source file SHA-256 bindings were declared."))
    if len(hashes) > MAX_SOURCE_FILES:
        failures.append(_failure("too_many_source_files", "Source binding count exceeds the proof limit."))

    declared_files = _mapping(spec.get("c_boundary")).get("files")
    payload_files = _mapping(payload.get("harness_contract")).get("source_files")
    if not isinstance(declared_files, list) or payload_files != declared_files:
        failures.append(_failure("source_contract_mismatch", "Fresh harness source bindings do not match the spec."))

    bindings: list[dict[str, Any]] = []
    for raw_path, expected in sorted(hashes.items())[:MAX_SOURCE_FILES]:
        path = _safe_path(base, raw_path, "source file", failures)
        actual = _file_sha(path, "source file", failures)
        if not _valid_sha(expected):
            failures.append(_failure("source_hash_missing", "Source file requires an exact SHA-256 binding."))
            match_mode = None
        elif path is None or actual is None:
            match_mode = None
        else:
            match_mode = path_hash_match_mode(path, str(expected).lower(), actual_sha256=actual)
            if match_mode is None:
                failures.append(_failure("source_hash_mismatch", "Source file SHA-256 drifted."))
        binding = {"path": _logical(base, path), "sha256": actual or "invalid"}
        if _valid_sha(expected):
            binding["declared_sha256"] = str(expected).lower()
        if match_mode is not None:
            binding["hash_match_mode"] = match_mode
        bindings.append(binding)

    span = spec.get("function_source_span")
    if not isinstance(span, Mapping):
        signatures = _mapping(spec.get("c_boundary")).get("signatures")
        if isinstance(signatures, Sequence) and signatures and isinstance(signatures[0], Mapping):
            span = signatures[0].get("source_span")
    span_binding = _span_binding(base, span, failures)
    return bindings, span_binding


def _span_binding(base: Path, span: Any, failures: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(span, Mapping):
        failures.append(_failure("source_span_missing", "Function source span is missing."))
        return {"status": "invalid"}
    path = _safe_path(base, span.get("file"), "source span", failures)
    expected = span.get("sha256")
    data: bytes | None = None
    coordinates: dict[str, int] = {}
    coordinate_match_mode = None
    if not _valid_sha(expected):
        failures.append(_failure("source_span_hash_mismatch", "Function source span SHA-256 drifted."))
    if path is not None and path.is_file() and _valid_sha(expected):
        try:
            data, coordinates, coordinate_match_mode = extract_strict_span(
                path,
                dict(span),
                str(expected).lower(),
                max_span_bytes=MAX_SPAN_BYTES,
            )
        except ValueError:
            data = None
    actual = hashlib.sha256(data).hexdigest() if data is not None else None
    match_mode = None
    if data is None:
        failures.append(_failure("source_span_invalid", "Source span bounds are invalid or too large."))
        if _valid_sha(expected):
            failures.append(_failure("source_span_hash_mismatch", "Function source span SHA-256 drifted."))
    elif _valid_sha(expected):
        match_mode = bytes_hash_match_mode(data, str(expected).lower(), actual_sha256=actual)
        if match_mode is None:
            failures.append(_failure("source_span_hash_mismatch", "Function source span SHA-256 drifted."))
    binding = {"path": _logical(base, path), "sha256": actual or "invalid", **coordinates}
    if _valid_sha(expected):
        binding["declared_sha256"] = str(expected).lower()
    if match_mode is not None:
        binding["hash_match_mode"] = match_mode
    if coordinate_match_mode is not None:
        binding["coordinate_match_mode"] = coordinate_match_mode
    return binding


def _compile_binding(
    spec: Mapping[str, Any], payload: Mapping[str, Any], harness: Path | None, root: Path,
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    command = payload.get("compile_command_draft")
    execution = payload.get("compile_execution")
    if not isinstance(command, Mapping) or not isinstance(execution, Mapping):
        failures.append(_failure("compile_evidence_missing", "Compile command or execution payload is missing."))
        return {"flags": {}}
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or len(argv) > MAX_ARGV_ITEMS or not all(isinstance(v, str) for v in argv):
        failures.append(_failure("compile_command_invalid", "Compile command argv is missing or exceeds limits."))
        argv = []
    if execution.get("argv") != argv:
        failures.append(_failure("compile_command_mismatch", "Compile execution is not bound to the draft command."))
    if harness is not None and harness.name not in argv:
        failures.append(_failure("harness_not_compiled", "Compile command does not reference the fresh harness."))
    profile = _mapping(spec.get("build_profile"))
    defines = [str(item) for item in profile.get("defines", [])] if isinstance(profile.get("defines", []), list) else []
    if command.get("defines") != defines or any(f"-D{item}" not in argv for item in defines):
        failures.append(_failure("build_profile_mismatch", "Compile defines do not match the build profile."))
    if command.get("status") != "draft_not_executed":
        failures.append(_failure("compile_command_status_invalid", "Compile command draft status is invalid."))

    compile_status = execution.get("status")
    if compile_status != "compile_succeeded_not_oracle":
        kind = "compiler_not_found" if compile_status == "compiler_not_found" else "compile_failed"
        failures.append(_failure(kind, "Fresh C harness compile did not succeed."))
    if execution.get("attempted") is not True or execution.get("returncode") != 0:
        failures.append(_failure("compile_execution_invalid", "Compile execution was not attempted successfully."))
    toolchain_status = execution.get("toolchain_status_after_attempt")
    if toolchain_status is None:
        toolchain_status = payload.get("toolchain_status")
    if toolchain_status != "COMPILE_SUCCEEDED_NOT_ORACLE":
        failures.append(_failure("toolchain_status_mismatch", "Compile and toolchain statuses are inconsistent."))
    if compile_status != "compile_succeeded_not_oracle" and toolchain_status == "COMPILE_SUCCEEDED_NOT_ORACLE":
        failures.append(_failure("toolchain_status_mismatch", "Failed compile has a contradictory success status."))
    for duplicate_key in ("toolchain_status", "toolchain_status_after_attempt"):
        duplicate = payload.get(duplicate_key)
        if duplicate is not None and duplicate != toolchain_status:
            failures.append(_failure("toolchain_status_mismatch", "Duplicate toolchain statuses are inconsistent."))
    actual_argv = execution.get("execution_argv")
    if not isinstance(actual_argv, list) or not actual_argv:
        failures.append(_failure("compile_tool_identity_missing", "Actual compiler invocation identity is missing."))

    run = execution.get("harness_execution")
    if not isinstance(run, Mapping):
        failures.append(_failure("harness_execution_missing", "Fresh harness execution is missing."))
        run = {}
    if run.get("status") != "exited_zero_not_oracle" or run.get("attempted") is not True or run.get("returncode") != 0:
        failures.append(_failure("harness_execution_failed", "Fresh harness did not exit successfully."))
    run_argv = run.get("execution_argv", run.get("argv"))
    if not isinstance(run_argv, list) or not run_argv:
        failures.append(_failure("harness_tool_identity_missing", "Actual harness invocation identity is missing."))
    top_run = payload.get("harness_execution")
    if top_run is not None and top_run != run:
        failures.append(_failure("harness_execution_conflict", "Duplicate harness execution payloads are inconsistent."))
    gate = run.get("output_gate")
    if not isinstance(gate, Mapping):
        failures.append(_failure("output_gate_missing", "Fresh harness output gate is missing."))
        gate = {}
    if gate.get("status") != "matched_not_oracle" or gate.get("missing_stdout_fragments") != []:
        failures.append(_failure("oracle_output_mismatch", "Fresh harness output did not match every fixture marker."))
    if not isinstance(gate.get("matched_stdout_fragments"), list) or not gate.get("matched_stdout_fragments"):
        failures.append(_failure("oracle_output_unproven", "Fresh harness has no matched fixture markers."))
    for duplicate in (execution.get("output_gate"), payload.get("output_gate")):
        if duplicate is not None and duplicate != gate:
            failures.append(_failure("output_gate_conflict", "Duplicate output gate payloads are inconsistent."))

    flags = {
        "argv": _compile_flags(argv, harness, command),
        "compiler_command_source": profile.get("compiler_command_source"),
        "defines": defines,
        "include_paths": profile.get("include_paths", []),
        "link_source_files": profile.get("link_source_files", []),
        "preprocessing_mode": profile.get("preprocessing_mode"),
    }
    execution_identity = {
        "actual_argv_sha256": _hash_json(sanitize_value(actual_argv, [str(root)])),
        "harness_argv_sha256": _hash_json(sanitize_value(run_argv, [str(root)])),
        "output_gate_sha256": _hash_json(sanitize_value(gate, [str(root)])),
        "compiler_name": execution.get("compiler_name"),
        "toolchain_adapter": execution.get("toolchain_adapter"),
        "compile_status": execution.get("status"),
        "run_status": run.get("status"),
        "output_status": gate.get("status"),
    }
    return {
        "flags": flags,
        "compile_command_sha256": _hash_json(command),
        "compile_execution_sha256": _hash_json(execution_identity),
    }


def _compile_flags(argv: list[str], harness: Path | None, command: Mapping[str, Any]) -> list[str]:
    excluded = {harness.name} if harness is not None else set()
    links = command.get("link_source_files")
    if isinstance(links, list):
        for item in links:
            if isinstance(item, Mapping):
                excluded.update(str(item.get(key)) for key in ("path", "resolved_path") if item.get(key))
    flags: list[str] = []
    skip_output = False
    for item in argv[1:]:
        if skip_output:
            skip_output = False
            continue
        if item == "-o":
            skip_output = True
            continue
        if item not in excluded:
            flags.append(item)
    return flags


def _verify_ref(
    root: Path, ref: Mapping[str, Any], expected_path: Path | None, expected_sha: str | None,
    label: str, failures: list[dict[str, Any]],
) -> None:
    path = _safe_path(root, ref.get("path"), f"{label} reference", failures)
    if path != expected_path:
        failures.append(_failure(f"{label}_path_mismatch", f"{label.title()} reference points to another file."))
    declared_sha = ref.get("sha256")
    if not _valid_sha(declared_sha) or str(declared_sha).lower() != expected_sha:
        failures.append(_failure(f"{label}_hash_mismatch", f"{label.title()} reference SHA-256 drifted."))


def _safe_path(root: Path, value: Any, label: str, failures: list[dict[str, Any]]) -> Path | None:
    if not isinstance(value, (str, Path)) or not str(value):
        failures.append(_failure("path_missing", f"{label.title()} path is missing."))
        return None
    try:
        candidate = Path(value)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            resolved.relative_to(root.resolve())
            return resolved
        return resolve_under(root, value)
    except (OSError, ValueError):
        failures.append(_failure("path_escape", f"{label.title()} path escapes the proof root."))
        return None


def _file_sha(path: Path | None, label: str, failures: list[dict[str, Any]]) -> str | None:
    if path is None or not path.is_file():
        failures.append(_failure("file_missing", f"{label.title()} file is missing."))
        return None
    try:
        return sha256_path(path)
    except OSError:
        failures.append(_failure("file_unreadable", f"{label.title()} file cannot be read."))
        return None


def _failure(kind: str, message: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    text = redact_metadata_text(message).strip() or "Fresh oracle verification failed."
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_MESSAGE_BYTES:
        text = encoded[: MAX_MESSAGE_BYTES - 3].decode("utf-8", errors="ignore") + "..."
    result: dict[str, Any] = {"gate": "c_oracle", "kind": kind[:128], "message": text}
    if details:
        safe = sanitize_value(dict(details))
        if len(json.dumps(safe, sort_keys=True, ensure_ascii=False).encode("utf-8")) <= MAX_DETAILS_BYTES:
            result["details"] = safe
    return result


def _result(identity: Mapping[str, Any], failures: list[dict[str, Any]]) -> dict[str, Any]:
    bounded = failures[:MAX_FAILURES]
    run = _mapping(identity.get("run"))
    result = {
        "schema_version": 1,
        "status": "failed" if bounded else "passed",
        "oracle_run_sha256": _hash_json(run),
        "failures": bounded,
    }
    if not bounded:
        result["reuse_key_sha256"] = run.get("reuse_key_sha256")
        result["bindings"] = identity.get("bindings")
        result.update(_mapping(identity.get("proof")))
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value.lower()) is not None


def _hash_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _logical(root: Path, path: Path | None) -> str:
    if path is None:
        return "<invalid>"
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return "<invalid>"
    return "<proof-root>" if not relative.parts else f"<proof-root>/{relative.as_posix()}"
