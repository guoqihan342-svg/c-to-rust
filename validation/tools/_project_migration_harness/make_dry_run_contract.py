from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .make_dry_run_binding import (
    validated_working_directory,
)
from .make_dry_run_contract_refs import (
    MakeDryRunContractError, artifact_ref as _artifact_ref,
    artifact_refs as _artifact_refs, fail as _fail,
    fixed_argv as _fixed_make_argv, require_raw_cas_ref as _cas_raw_ref,
    require_snapshot_cas_ref as _cas_snapshot_ref, targets as _targets,
)
from .make_dry_run_parser import (
    MAX_STDOUT_BYTES,
    PARSER_NAME,
    PARSER_VERSION,
    parse_make_dry_run_stdout,
    validate_make_dry_run_commands,
)
from .make_dry_run_result import (
    MakeDryRunOutcome, validate_successful_make_outcome,
)


MAKE_DRY_RUN_REPORT_SCHEMA_VERSION = 3
MAKE_DRY_RUN_REPORT_KIND = "project-migration-make-dry-run-report"
COLLECTION_MODE = "explicit-make-dry-run"
MAX_STDERR_BYTES = 1024 * 1024
_REPORT_FIELDS = {
    "schema_version", "artifact_kind", "status", "collection_mode",
    "explicitly_enabled", "make_argv", "targets", "working_directory",
    "parser", "raw_stdout", "raw_stdout_ref", "raw_stderr_ref",
    "makefile_ref", "source_refs", "input_refs", "repository_snapshot_ref",
    "toolchain_ref",
    "sandbox_ref", "execution_plan_ref", "commands", "command_count",
    "execution_plan_sha256",
    "configure_executed", "make_started", "returncode", "timed_out",
    "output_flooded", "semantic_gate", "translation_coverage_numerator",
    "report_sha256",
}


def create_make_dry_run_report(
    *,
    outcome: MakeDryRunOutcome,
    raw_stdout_ref: Mapping[str, Any],
    raw_stderr_ref: Mapping[str, Any],
    makefile_ref: Mapping[str, Any],
    source_refs: Sequence[Mapping[str, Any]],
    input_refs: Sequence[Mapping[str, Any]],
    toolchain_ref: Mapping[str, Any],
    sandbox_ref: Mapping[str, Any],
    execution_plan_ref: Mapping[str, Any],
    targets: Sequence[str],
    working_directory: str = ".",
    repository_snapshot_ref: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        execution = validate_successful_make_outcome(outcome)
    except ValueError as error:
        raise MakeDryRunContractError(str(error)) from error
    assert execution.stdout is not None and execution.stderr is not None
    try:
        workdir = validated_working_directory(working_directory)
    except ValueError as error:
        raise MakeDryRunContractError(str(error)) from error
    parsed = parse_make_dry_run_stdout(
        execution.stdout, working_directory=workdir,
    )
    makefile = _artifact_ref(makefile_ref, "makefile")
    sources = sorted(
        (_artifact_ref(value, "source") for value in source_refs),
        key=lambda value: value["path"],
    )
    inputs = sorted(
        (_artifact_ref(value, "input") for value in input_refs),
        key=lambda value: value["path"],
    )
    snapshot = (
        _artifact_ref(repository_snapshot_ref, "repository_snapshot")
        if repository_snapshot_ref is not None else None
    )
    if snapshot is not None:
        _cas_snapshot_ref(snapshot)
    toolchain = _artifact_ref(toolchain_ref, "toolchain")
    sandbox = _artifact_ref(sandbox_ref, "sandbox")
    plan = _artifact_ref(execution_plan_ref, "execution_plan")
    stdout_ref = _artifact_ref(raw_stdout_ref, "stdout")
    stderr_ref = _artifact_ref(raw_stderr_ref, "stderr")
    if (
        stdout_ref["sha256"] != hashlib.sha256(execution.stdout).hexdigest()
        or stdout_ref["size_bytes"] != len(execution.stdout)
        or stderr_ref["sha256"] != hashlib.sha256(execution.stderr).hexdigest()
        or stderr_ref["size_bytes"] != len(execution.stderr)
        or sandbox["sha256"] != execution.sandbox_sha256
    ):
        _fail("make_dry_run_outcome_raw_binding_mismatch")
    if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)):
        _fail("make_dry_run_targets_invalid")
    normalized_targets = _targets(targets)
    make_argv = _fixed_make_argv(
        makefile["path"], normalized_targets, workdir,
    )
    core = {
        "schema_version": MAKE_DRY_RUN_REPORT_SCHEMA_VERSION,
        "artifact_kind": MAKE_DRY_RUN_REPORT_KIND,
        "status": "ready",
        "collection_mode": COLLECTION_MODE,
        "explicitly_enabled": True,
        "make_argv": make_argv,
        "targets": normalized_targets,
        "working_directory": workdir,
        "parser": dict(parsed["parser"]),
        "raw_stdout": dict(parsed["raw_stdout"]),
        "raw_stdout_ref": stdout_ref,
        "raw_stderr_ref": stderr_ref,
        "makefile_ref": makefile,
        "source_refs": sources,
        "input_refs": inputs,
        "repository_snapshot_ref": snapshot,
        "toolchain_ref": toolchain,
        "sandbox_ref": sandbox,
        "execution_plan_ref": plan,
        "execution_plan_sha256": execution.plan_sha256,
        "commands": parsed["commands"],
        "command_count": len(parsed["commands"]),
        "configure_executed": False,
        "make_started": execution.make_started,
        "returncode": execution.returncode,
        "timed_out": execution.timed_out,
        "output_flooded": execution.output_flooded,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    report = {**core, "report_sha256": content_sha256(core)}
    return validate_make_dry_run_report(report)


def validate_make_dry_run_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        _fail("make_dry_run_report_fields_invalid")
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != MAKE_DRY_RUN_REPORT_SCHEMA_VERSION
        or value.get("artifact_kind") != MAKE_DRY_RUN_REPORT_KIND
        or value.get("status") != "ready"
        or value.get("collection_mode") != COLLECTION_MODE
        or value.get("explicitly_enabled") is not True
        or value.get("configure_executed") is not False
        or value.get("make_started") is not True
        or type(value.get("returncode")) is not int
        or value.get("returncode") != 0
        or value.get("timed_out") is not False
        or value.get("output_flooded") is not False
        or value.get("semantic_gate") is not False
        or type(value.get("translation_coverage_numerator")) is not int
        or value.get("translation_coverage_numerator") != 0
    ):
        _fail("make_dry_run_report_policy_invalid")
    try:
        workdir = validated_working_directory(value.get("working_directory"))
    except ValueError as error:
        raise MakeDryRunContractError(
            "make_dry_run_report_working_directory_invalid"
        ) from error
    parser = value.get("parser")
    if (
        not isinstance(parser, Mapping)
        or set(parser) != {"name", "version"}
        or parser.get("name") != PARSER_NAME
        or type(parser.get("version")) is not int
        or parser.get("version") not in {2, PARSER_VERSION}
    ):
        _fail("make_dry_run_report_parser_invalid")
    raw = value.get("raw_stdout")
    size = raw.get("size_bytes") if isinstance(raw, Mapping) else None
    if (
        not isinstance(raw, Mapping)
        or set(raw) != {"encoding", "sha256", "size_bytes"}
        or raw.get("encoding") != "utf-8"
        or not is_sha256(raw.get("sha256"))
        or isinstance(size, bool)
        or not isinstance(size, int)
        or not 0 < size <= MAX_STDOUT_BYTES
    ):
        _fail("make_dry_run_report_stdout_invalid")
    makefile = _artifact_ref(value.get("makefile_ref"), "makefile")
    toolchain = _artifact_ref(value.get("toolchain_ref"), "toolchain")
    sandbox = _artifact_ref(value.get("sandbox_ref"), "sandbox")
    plan = _artifact_ref(value.get("execution_plan_ref"), "execution_plan")
    if not is_sha256(value.get("execution_plan_sha256")):
        _fail("make_dry_run_report_execution_plan_sha256_invalid")
    stdout_ref = _artifact_ref(value.get("raw_stdout_ref"), "stdout")
    stderr_ref = _artifact_ref(value.get("raw_stderr_ref"), "stderr")
    _cas_raw_ref(stdout_ref, "raw-stdout")
    _cas_raw_ref(stderr_ref, "raw-stderr")
    if stdout_ref["sha256"] != raw["sha256"] or stdout_ref["size_bytes"] != size:
        _fail("make_dry_run_report_stdout_binding_mismatch")
    if stderr_ref["size_bytes"] > MAX_STDERR_BYTES:
        _fail("make_dry_run_report_stderr_invalid")
    sources = _artifact_refs(value.get("source_refs"), "source")
    inputs = _artifact_refs(value.get("input_refs"), "input")
    snapshot_value = value.get("repository_snapshot_ref")
    snapshot = (
        _artifact_ref(snapshot_value, "repository_snapshot")
        if snapshot_value is not None else None
    )
    if snapshot is not None:
        _cas_snapshot_ref(snapshot)
    source_paths = [item["path"] for item in sources]
    input_paths = [item["path"] for item in inputs]
    targets = _targets(value.get("targets"))
    expected_make_argv = _fixed_make_argv(makefile["path"], targets, workdir)
    if value.get("make_argv") != expected_make_argv:
        _fail("make_dry_run_report_make_argv_invalid")
    try:
        commands = validate_make_dry_run_commands(
            value.get("commands"), working_directory=workdir,
        )
    except ValueError as error:
        raise MakeDryRunContractError(
            "make_dry_run_report_command_binding_invalid"
        ) from error
    if type(value.get("command_count")) is not int or value.get("command_count") != len(commands):
        _fail("make_dry_run_report_command_count_invalid")
    compiled_sources = sorted({
        source for command in commands if command["kind"] == "compile"
        for source in command["inputs"]
    })
    if compiled_sources != source_paths:
        _fail("make_dry_run_report_source_binding_mismatch")
    produced = {path for command in commands for path in command["outputs"]}
    leaf_inputs = sorted({
        path for command in commands for path in command["inputs"]
        if path not in produced
    })
    if leaf_inputs != input_paths or not set(source_paths).issubset(input_paths):
        _fail("make_dry_run_report_input_binding_mismatch")
    core = {key: value[key] for key in _REPORT_FIELDS if key != "report_sha256"}
    if value.get("report_sha256") != content_sha256(core):
        _fail("make_dry_run_report_sha256_invalid")
    return {
        **dict(value),
        "makefile_ref": makefile,
        "source_refs": sources,
        "input_refs": inputs,
        "repository_snapshot_ref": snapshot,
        "toolchain_ref": toolchain,
        "sandbox_ref": sandbox,
        "execution_plan_ref": plan,
        "raw_stdout_ref": stdout_ref,
        "raw_stderr_ref": stderr_ref,
        "commands": commands,
    }


def canonical_make_dry_run_report_bytes(value: Any) -> bytes:
    return canonical_json_bytes(validate_make_dry_run_report(value))


build_make_dry_run_report = create_make_dry_run_report

__all__ = [
    "COLLECTION_MODE",
    "MAKE_DRY_RUN_REPORT_KIND",
    "MAKE_DRY_RUN_REPORT_SCHEMA_VERSION",
    "MAX_STDERR_BYTES",
    "MakeDryRunContractError",
    "build_make_dry_run_report",
    "canonical_make_dry_run_report_bytes",
    "create_make_dry_run_report",
    "validate_make_dry_run_report",
]
