from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
import re
from typing import Any

from .artifacts import content_sha256


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[/\\]")
_REPORT_FIELDS = {
    "schema_version", "artifact_kind", "status", "blockers", "run_id",
    "inputs", "tools", "policy", "executions", "generated",
    "artifact_refs", "claims", "semantic_gate", "translation_coverage_numerator",
}
_EXECUTION_FIELDS = {
    "schema_version", "artifact_kind", "purpose", "status", "argv",
    "argv_sha256", "local_execution_binding_sha256", "working_directory",
    "environment_keys", "environment_sha256", "timeout_seconds",
    "command_started", "timed_out", "returncode", "output_limit_exceeded",
    "stdout_sha256", "stderr_sha256", "stdout_ref", "stderr_ref",
    "semantic_gate", "translation_coverage_numerator",
}


def validate_c2rust_baseline_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise ValueError("c2rust_baseline_report_fields_invalid")
    report = dict(value)
    status = report.get("status")
    blockers = report.get("blockers")
    if (
        report.get("schema_version") != 1
        or report.get("artifact_kind") != "c2rust-project-baseline-report"
        or status not in {"passed", "blocked"}
        or not isinstance(blockers, list)
        or any(not isinstance(item, str) or not item for item in blockers)
        or (status == "passed") != (not blockers)
        or _SHA256.fullmatch(str(report.get("run_id"))) is None
        or report.get("semantic_gate") is not False
        or report.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("c2rust_baseline_report_policy_invalid")
    _validate_inputs(report.get("inputs"))
    _validate_tools(report.get("tools"))
    _validate_policy(report.get("policy"))
    executions = _validate_executions(report.get("executions"))
    wrappers, manifests = _validate_generated(report.get("generated"))
    _validate_artifact_refs(report.get("artifact_refs"))
    _validate_claims(report.get("claims"), status)
    _validate_completion(status, executions, wrappers, manifests)
    _reject_absolute_paths(report)
    return report


def _validate_inputs(value: Any) -> None:
    fields = {
        "repository_identity_sha256", "compile_commands_path",
        "original_compile_database_ref", "normalized_compile_database_ref",
        "source_bindings",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c2rust_baseline_inputs_invalid")
    compile_path = _relative(value.get("compile_commands_path"))
    sources = value.get("source_bindings")
    if not isinstance(sources, list) or not sources:
        raise ValueError("c2rust_baseline_sources_invalid")
    for source in sources:
        if (
            not isinstance(source, Mapping)
            or set(source) != {"path", "sha256", "size_bytes"}
            or _relative(source.get("path")) is None
            or _SHA256.fullmatch(str(source.get("sha256"))) is None
            or type(source.get("size_bytes")) is not int
            or source["size_bytes"] < 0
        ):
            raise ValueError("c2rust_baseline_source_binding_invalid")
    expected = content_sha256({
        "compile_commands_path": compile_path, "source_bindings": sources,
    })
    if value.get("repository_identity_sha256") != expected:
        raise ValueError("c2rust_baseline_repository_identity_invalid")


def _validate_tools(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("c2rust_baseline_tools_invalid")
    roles = set()
    for tool in value:
        fields = {
            "role", "basename", "sha256", "size_bytes",
            "portable_identity_sha256",
        }
        if not isinstance(tool, Mapping) or set(tool) != fields:
            raise ValueError("c2rust_baseline_tool_invalid")
        core = {key: tool[key] for key in fields - {"portable_identity_sha256"}}
        if (
            not isinstance(tool.get("role"), str)
            or not isinstance(tool.get("basename"), str)
            or "/" in tool["basename"] or "\\" in tool["basename"]
            or _SHA256.fullmatch(str(tool.get("sha256"))) is None
            or type(tool.get("size_bytes")) is not int or tool["size_bytes"] < 0
            or tool.get("portable_identity_sha256") != content_sha256(core)
        ):
            raise ValueError("c2rust_baseline_tool_identity_invalid")
        roles.add(tool["role"])
    if roles != {"c2rust-transpile", "cargo", "rustc"}:
        raise ValueError("c2rust_baseline_tool_roles_invalid")


def _validate_policy(value: Any) -> None:
    fields = {
        "timeout_seconds", "minimal_environment", "cargo_offline",
        "cargo_check_all_targets", "all_discovered_wrappers_required",
        "cargo_toolchain", "environment_override_keys",
        "environment_overrides_sha256", "rustc_bootstrap",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c2rust_baseline_policy_invalid")
    keys = value.get("environment_override_keys")
    if (
        type(value.get("timeout_seconds")) is not int
        or not 1 <= value["timeout_seconds"] <= 3_600
        or any(value.get(key) is not True for key in (
            "minimal_environment", "cargo_offline", "cargo_check_all_targets",
            "all_discovered_wrappers_required",
        ))
        or value.get("cargo_toolchain") is not None
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value["cargo_toolchain"]) is None
        or not isinstance(keys, list) or keys != sorted(set(keys))
        or set(keys) - {"CARGO_HOME", "RUSTUP_HOME", "RUSTC_BOOTSTRAP"}
        or _SHA256.fullmatch(str(value.get("environment_overrides_sha256"))) is None
        or type(value.get("rustc_bootstrap")) is not bool
        or value["rustc_bootstrap"] != ("RUSTC_BOOTSTRAP" in keys)
    ):
        raise ValueError("c2rust_baseline_policy_contract_invalid")


def _validate_executions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("c2rust_baseline_executions_invalid")
    result = []
    for execution in value:
        if not isinstance(execution, Mapping) or set(execution) != _EXECUTION_FIELDS:
            raise ValueError("c2rust_baseline_execution_invalid")
        passed = (
            execution.get("command_started") is True
            and execution.get("timed_out") is False
            and execution.get("returncode") == 0
            and execution.get("output_limit_exceeded") is False
        )
        if (
            execution.get("schema_version") != 1
            or execution.get("artifact_kind") != "c2rust-project-process-execution"
            or execution.get("status") != ("passed" if passed else "failed")
            or not isinstance(execution.get("argv"), list)
            or execution.get("argv_sha256") != content_sha256(execution["argv"])
            or _relative(execution.get("working_directory")) is None
            or execution.get("semantic_gate") is not False
            or execution.get("translation_coverage_numerator") != 0
        ):
            raise ValueError("c2rust_baseline_execution_contract_invalid")
        result.append(dict(execution))
    return result


def _validate_generated(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    fields = {"workspace", "snapshot_ref", "manifests", "wrappers", "repairs"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c2rust_baseline_generated_invalid")
    _relative(value.get("workspace"))
    manifests = value.get("manifests")
    wrappers = value.get("wrappers")
    if (
        not isinstance(manifests, list) or not isinstance(wrappers, list)
        or any(_relative(item) is None for item in manifests)
        or any(not isinstance(item, dict) for item in wrappers)
        or not isinstance(value.get("repairs"), list)
    ):
        raise ValueError("c2rust_baseline_generated_contract_invalid")
    return wrappers, manifests


def _validate_artifact_refs(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("c2rust_baseline_artifact_refs_invalid")
    if any(
        not isinstance(item, Mapping)
        or set(item) != {"role", "visibility", "ref"}
        or item.get("visibility") != "private-local"
        for item in value
    ):
        raise ValueError("c2rust_baseline_artifact_ref_invalid")


def _validate_claims(value: Any, status: str) -> None:
    expected = {
        "classification": "execution-evidence-only",
        "publication_scope": "portable-summary-only",
        "referenced_artifact_visibility": "private-local",
        "host_absolute_paths_in_report": False,
        "real_process_exit_zero": status == "passed",
        "ai_translation": False,
        "final_semantic_gate": False,
    }
    if value != expected:
        raise ValueError("c2rust_baseline_claims_invalid")


def _validate_completion(
    status: str, executions: list[dict[str, Any]],
    wrappers: list[dict[str, Any]], manifests: list[str],
) -> None:
    purposes = [item.get("purpose") for item in executions]
    if purposes.count("c2rust-transpile-project") != 1:
        raise ValueError("c2rust_baseline_transpiler_evidence_invalid")
    if status != "passed":
        return
    wrapper_names = {item.get("name") for item in wrappers}
    run_purposes = {
        str(item)[len("cargo-run-wrapper-"):]
        for item in purposes if str(item).startswith("cargo-run-wrapper-")
    }
    check_count = sum(str(item).startswith("cargo-check-all-targets-") for item in purposes)
    if (
        not wrappers or not manifests or any(item["status"] != "passed" for item in executions)
        or run_purposes != wrapper_names or len(run_purposes) != len(wrappers)
        or check_count != len(manifests)
    ):
        raise ValueError("c2rust_baseline_completion_evidence_invalid")


def _reject_absolute_paths(value: Any) -> None:
    if isinstance(value, str):
        if value.startswith(("/", "\\\\")) or _WINDOWS_ABSOLUTE.match(value):
            raise ValueError("c2rust_baseline_public_absolute_path_forbidden")
    elif isinstance(value, Mapping):
        for child in value.values():
            _reject_absolute_paths(child)
    elif isinstance(value, list):
        for child in value:
            _reject_absolute_paths(child)


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("c2rust_baseline_relative_path_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError("c2rust_baseline_relative_path_invalid")
    return value


__all__ = ["validate_c2rust_baseline_report"]
