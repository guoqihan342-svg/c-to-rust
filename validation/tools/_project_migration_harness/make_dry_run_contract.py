from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
import re
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256, safe_posix_path
from .make_dry_run_parser import (
    MAX_STDOUT_BYTES,
    PARSER_NAME,
    PARSER_VERSION,
    parse_make_dry_run_stdout,
    validate_make_dry_run_commands,
)


MAKE_DRY_RUN_REPORT_SCHEMA_VERSION = 1
MAKE_DRY_RUN_REPORT_KIND = "project-migration-make-dry-run-report"
COLLECTION_MODE = "explicit-make-dry-run"
MAX_TARGETS = 64
MAX_TARGET_BYTES = 256
_REPORT_FIELDS = {
    "schema_version", "artifact_kind", "status", "collection_mode",
    "explicitly_enabled", "make_argv", "targets", "working_directory",
    "parser", "raw_stdout", "makefile_ref", "source_refs", "toolchain_ref",
    "sandbox_ref", "commands", "command_count", "configure_executed",
    "semantic_gate", "translation_coverage_numerator", "report_sha256",
}


class MakeDryRunContractError(ValueError):
    pass


def create_make_dry_run_report(
    *,
    stdout: str | bytes,
    makefile_ref: Mapping[str, Any],
    source_refs: Sequence[Mapping[str, Any]],
    toolchain_ref: Mapping[str, Any],
    sandbox_ref: Mapping[str, Any],
    targets: Sequence[str],
) -> dict[str, Any]:
    parsed = parse_make_dry_run_stdout(stdout)
    makefile = _artifact_ref(makefile_ref, "makefile")
    sources = sorted(
        (_artifact_ref(value, "source") for value in source_refs),
        key=lambda value: value["path"],
    )
    toolchain = _artifact_ref(toolchain_ref, "toolchain")
    sandbox = _artifact_ref(sandbox_ref, "sandbox")
    if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)):
        _fail("make_dry_run_targets_invalid")
    normalized_targets = _targets(list(targets))
    make_argv = [
        "make", "-B", "-n", "-j1", "--no-print-directory",
        "-f", makefile["path"], "--", *normalized_targets,
    ]
    core = {
        "schema_version": MAKE_DRY_RUN_REPORT_SCHEMA_VERSION,
        "artifact_kind": MAKE_DRY_RUN_REPORT_KIND,
        "status": "ready",
        "collection_mode": COLLECTION_MODE,
        "explicitly_enabled": True,
        "make_argv": make_argv,
        "targets": normalized_targets,
        "working_directory": ".",
        "parser": dict(parsed["parser"]),
        "raw_stdout": dict(parsed["raw_stdout"]),
        "makefile_ref": makefile,
        "source_refs": sources,
        "toolchain_ref": toolchain,
        "sandbox_ref": sandbox,
        "commands": parsed["commands"],
        "command_count": len(parsed["commands"]),
        "configure_executed": False,
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
        or value.get("working_directory") != "."
        or value.get("configure_executed") is not False
        or value.get("semantic_gate") is not False
        or type(value.get("translation_coverage_numerator")) is not int
        or value.get("translation_coverage_numerator") != 0
    ):
        _fail("make_dry_run_report_policy_invalid")
    parser = value.get("parser")
    if (
        not isinstance(parser, Mapping)
        or set(parser) != {"name", "version"}
        or parser.get("name") != PARSER_NAME
        or type(parser.get("version")) is not int
        or parser.get("version") != PARSER_VERSION
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
    raw_sources = value.get("source_refs")
    if not isinstance(raw_sources, list) or not raw_sources:
        _fail("make_dry_run_report_source_refs_invalid")
    sources = [_artifact_ref(item, "source") for item in raw_sources]
    source_paths = [item["path"] for item in sources]
    if source_paths != sorted(set(source_paths)):
        _fail("make_dry_run_report_source_refs_not_canonical")
    targets = _targets(value.get("targets"))
    expected_make_argv = [
        "make", "-B", "-n", "-j1", "--no-print-directory",
        "-f", makefile["path"], "--", *targets,
    ]
    if value.get("make_argv") != expected_make_argv:
        _fail("make_dry_run_report_make_argv_invalid")
    try:
        commands = validate_make_dry_run_commands(value.get("commands"))
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
    core = {key: value[key] for key in _REPORT_FIELDS if key != "report_sha256"}
    if value.get("report_sha256") != content_sha256(core):
        _fail("make_dry_run_report_sha256_invalid")
    return {
        **dict(value),
        "makefile_ref": makefile,
        "source_refs": sources,
        "toolchain_ref": toolchain,
        "sandbox_ref": sandbox,
        "commands": commands,
    }


def canonical_make_dry_run_report_bytes(value: Any) -> bytes:
    return canonical_json_bytes(validate_make_dry_run_report(value))


def _artifact_ref(value: Any, role: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256", "size_bytes"}:
        _fail(f"make_dry_run_{role}_ref_invalid")
    size = value.get("size_bytes")
    if (
        not safe_posix_path(value.get("path"))
        or not is_sha256(value.get("sha256"))
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        _fail(f"make_dry_run_{role}_ref_invalid")
    return {"path": value["path"], "sha256": value["sha256"], "size_bytes": size}


def _targets(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or not 0 < len(value) <= MAX_TARGETS
    ):
        _fail("make_dry_run_targets_invalid")
    result = list(value)
    for target in result:
        path = PurePosixPath(target) if isinstance(target, str) else None
        if (
            not isinstance(target, str)
            or not target
            or len(target.encode("utf-8")) > MAX_TARGET_BYTES
            or not re.fullmatch(r"[A-Za-z0-9_.+/@%=-]+", target)
            or target.startswith(("-", "~", "/"))
            or path is None
            or ".." in path.parts
            or path.as_posix() != target
        ):
            _fail("make_dry_run_target_invalid")
    if len(result) != len(set(result)):
        _fail("make_dry_run_targets_duplicate")
    return result


def _fail(code: str) -> None:
    raise MakeDryRunContractError(code)


build_make_dry_run_report = create_make_dry_run_report

__all__ = [
    "COLLECTION_MODE",
    "MAKE_DRY_RUN_REPORT_KIND",
    "MAKE_DRY_RUN_REPORT_SCHEMA_VERSION",
    "MakeDryRunContractError",
    "build_make_dry_run_report",
    "canonical_make_dry_run_report_bytes",
    "create_make_dry_run_report",
    "validate_make_dry_run_report",
]
