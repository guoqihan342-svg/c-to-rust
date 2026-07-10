from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .contract import ReporterError, behavior_fields, require_dict
from .source_binding import StaticContext, sha256_file

HOST_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\/]|/(?:tmp|mnt|home|root|Users?)/|\\wsl(?:$|.localhost)[\/])",
    re.IGNORECASE,
)
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
