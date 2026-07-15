from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .native_link_trace_json import (
    JsonObjectRequiredError, StrictJsonError, required_json_object,
)

CARGO_COMPILER_ARTIFACT_EVIDENCE_SCHEMA_VERSION = 1
MAX_CARGO_COMPILER_ARTIFACT_EVIDENCE_BYTES = 4 * 1024 * 1024
MAX_CARGO_COMPILER_ARTIFACT_JSON_LINE_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_DRIVE_PATH = re.compile(r"(?P<drive>[A-Za-z]):/(?P<tail>.+)\Z", re.ASCII)
_EVENT_KEYS = {
    "reason", "package_id", "manifest_path", "target", "profile",
    "features", "filenames", "executable", "fresh",
}
_ARTIFACT_KEYS = _EVENT_KEYS - {"reason"}
_TARGET_KEYS = {
    "kind", "crate_types", "name", "src_path", "edition", "doc",
    "doctest", "test",
}
_PROFILE_KEYS = {
    "opt_level", "debuginfo", "debug_assertions", "overflow_checks", "test",
}
_IGNORED_KEYS = {
    "compiler-message": {
        "reason", "package_id", "manifest_path", "target", "message",
    },
    "build-script-executed": {
        "reason", "package_id", "linked_libs", "linked_paths", "cfgs", "env",
        "out_dir",
    },
}
_EVIDENCE_KEYS = {
    "schema_version", "artifact_count", "artifacts", "artifact_set_sha256",
    "build_finished_success", "source_sha256", "interface_closure",
    "semantic_gate", "translation_coverage_numerator", "content_sha256",
}

class CargoCompilerArtifactEvidenceError(ValueError):
    def __init__(self, code: str, line_number: int | None = None) -> None:
        detail = code if line_number is None else f"{code}:line:{line_number}"
        super().__init__(detail)
        self.code = code
        self.line_number = line_number

def parse_cargo_compiler_artifact_evidence(data: bytes) -> dict[str, Any]:
    raw, text = _decode(data)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        _fail("cargo_compiler_artifact_jsonl_empty")
    artifacts: list[dict[str, Any]] = []
    finished = False
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        if not line:
            _fail("cargo_compiler_artifact_jsonl_blank_line", line_number)
        if _utf8_size(line) > MAX_CARGO_COMPILER_ARTIFACT_JSON_LINE_BYTES:
            _fail("cargo_compiler_artifact_json_line_limit", line_number)
        event = _json_object(line, line_number)
        reason = event.get("reason")
        if type(reason) is not str: _fail("cargo_compiler_artifact_reason_invalid", line_number)
        if reason == "build-finished":
            if finished:
                _fail("cargo_compiler_artifact_multiple_build_finished", line_number)
            if set(event) != {"reason", "success"}:
                _fail("cargo_compiler_artifact_build_finished_schema", line_number)
            if event.get("success") is not True:
                _fail("cargo_compiler_artifact_build_failed", line_number)
            finished = True
        elif finished:
            _fail("cargo_compiler_artifact_event_after_build_finished", line_number)
        elif reason == "compiler-artifact":
            artifacts.append(_artifact(event, line_number))
        elif reason in _IGNORED_KEYS:
            _ignored_event(event, line_number)
        else:
            _fail("cargo_compiler_artifact_unknown_event", line_number)
    if not finished:
        _fail("cargo_compiler_artifact_build_finished_missing")
    if not artifacts:
        _fail("cargo_compiler_artifact_event_missing")
    return _evidence(_ordered_unique(artifacts), hashlib.sha256(raw).hexdigest())

def validate_cargo_compiler_artifact_evidence(
    value: Mapping[str, Any], source: bytes | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _EVIDENCE_KEYS:
        _fail("cargo_compiler_artifact_evidence_schema")
    raw_artifacts = value.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("cargo_compiler_artifact_artifacts_invalid")
    artifacts = []
    for item in raw_artifacts:
        if not isinstance(item, Mapping) or set(item) != _ARTIFACT_KEYS:
            _fail("cargo_compiler_artifact_artifact_schema")
        artifacts.append(_artifact({"reason": "compiler-artifact", **dict(item)}, None))
    canonical = _ordered_unique(artifacts)
    if raw_artifacts != canonical:
        _fail("cargo_compiler_artifact_artifact_order_or_duplicate")
    source_sha = value.get("source_sha256")
    if not isinstance(source_sha, str) or _SHA256.fullmatch(source_sha) is None:
        _fail("cargo_compiler_artifact_source_sha256_invalid")
    if (
        value.get("schema_version") != CARGO_COMPILER_ARTIFACT_EVIDENCE_SCHEMA_VERSION
        or type(value.get("artifact_count")) is not int
        or value.get("artifact_count") != len(canonical)
        or value.get("build_finished_success") is not True
    ):
        _fail("cargo_compiler_artifact_summary_invalid")
    if (
        value.get("interface_closure") is not False
        or value.get("semantic_gate") is not False
        or type(value.get("translation_coverage_numerator")) is not int
        or value.get("translation_coverage_numerator") != 0
    ):
        _fail("cargo_compiler_artifact_claim_boundary")
    expected = _evidence(canonical, source_sha)
    if value.get("artifact_set_sha256") != expected["artifact_set_sha256"]:
        _fail("cargo_compiler_artifact_set_sha256_drift")
    if value.get("content_sha256") != expected["content_sha256"]:
        _fail("cargo_compiler_artifact_content_sha256_drift")
    if dict(value) != expected:
        _fail("cargo_compiler_artifact_evidence_not_canonical")
    if source is not None and expected != parse_cargo_compiler_artifact_evidence(source):
        _fail("cargo_compiler_artifact_source_reparse_drift")
    return expected

def _decode(data: bytes) -> tuple[bytes, str]:
    if type(data) is not bytes:
        raise TypeError("Cargo compiler-artifact evidence input must be bytes")
    if len(data) > MAX_CARGO_COMPILER_ARTIFACT_EVIDENCE_BYTES:
        _fail("cargo_compiler_artifact_input_limit")
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CargoCompilerArtifactEvidenceError(
            "cargo_compiler_artifact_input_not_utf8"
        ) from error

def _json_object(line: str, line_number: int) -> dict[str, Any]:
    try:
        return required_json_object(line)
    except JsonObjectRequiredError:
        _fail("cargo_compiler_artifact_json_object_required", line_number)
    except (json.JSONDecodeError, RecursionError, StrictJsonError) as error:
        raise CargoCompilerArtifactEvidenceError(
            "cargo_compiler_artifact_json_invalid", line_number,
        ) from error

def _artifact(event: Mapping[str, Any], line: int | None) -> dict[str, Any]:
    if set(event) != _EVENT_KEYS:
        _fail("cargo_compiler_artifact_event_schema", line)
    filenames = _paths(event.get("filenames"), "filenames", line)
    executable = event.get("executable")
    if executable is not None:
        executable = _path(executable, "executable", line)
        if executable not in filenames:
            _fail("cargo_compiler_artifact_executable_not_in_filenames", line)
    if type(event.get("fresh")) is not bool:
        _fail("cargo_compiler_artifact_fresh_invalid", line)
    return {
        "package_id": _text(event.get("package_id"), "package_id", line),
        "manifest_path": _path(event.get("manifest_path"), "manifest_path", line),
        "target": _target(event.get("target"), line),
        "profile": _profile(event.get("profile"), line),
        "features": _texts(event.get("features"), "features", line),
        "filenames": filenames, "executable": executable, "fresh": event["fresh"],
    }

def _target(value: Any, line: int | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TARGET_KEYS:
        _fail("cargo_compiler_artifact_target_schema", line)
    if any(type(value.get(key)) is not bool for key in ("doc", "doctest", "test")):
        _fail("cargo_compiler_artifact_target_boolean_invalid", line)
    return {
        "kind": _texts(value.get("kind"), "target.kind", line, True),
        "crate_types": _texts(value.get("crate_types"), "target.crate_types", line, True),
        "name": _text(value.get("name"), "target.name", line),
        "src_path": _path(value.get("src_path"), "target.src_path", line),
        "edition": _text(value.get("edition"), "target.edition", line),
        "doc": value["doc"], "doctest": value["doctest"], "test": value["test"],
    }

def _profile(value: Any, line: int | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PROFILE_KEYS:
        _fail("cargo_compiler_artifact_profile_schema", line)
    debuginfo = value.get("debuginfo")
    if debuginfo is not None and (type(debuginfo) is not int or debuginfo < 0):
        _fail("cargo_compiler_artifact_profile_debuginfo_invalid", line)
    if any(
        type(value.get(key)) is not bool
        for key in ("debug_assertions", "overflow_checks", "test")
    ):
        _fail("cargo_compiler_artifact_profile_boolean_invalid", line)
    return {
        "opt_level": _text(value.get("opt_level"), "profile.opt_level", line),
        "debuginfo": debuginfo, "debug_assertions": value["debug_assertions"],
        "overflow_checks": value["overflow_checks"], "test": value["test"],
    }

def _ignored_event(event: Mapping[str, Any], line: int) -> None:
    reason = event.get("reason")
    if set(event) != _IGNORED_KEYS[reason]:
        _fail("cargo_compiler_artifact_ignored_event_schema", line)
    _text(event.get("package_id"), "package_id", line)
    if reason == "compiler-message":
        if not isinstance(event.get("message"), Mapping):
            _fail("cargo_compiler_artifact_compiler_message_schema", line)
        _path(event.get("manifest_path"), "manifest_path", line)
        _target(event.get("target"), line)
        return
    for key in ("linked_libs", "linked_paths", "cfgs"):
        _texts(event.get(key), key, line)
    _path(event.get("out_dir"), "out_dir", line)
    env = event.get("env")
    if not isinstance(env, list):
        _fail("cargo_compiler_artifact_build_script_env", line)
    for pair in env:
        if not isinstance(pair, list) or len(pair) != 2:
            _fail("cargo_compiler_artifact_build_script_env", line)
        _text(pair[0], "env.name", line)
        _text(pair[1], "env.value", line)

def _text(value: Any, field: str, line: int | None, limit: int = 16384) -> str:
    if (
        type(value) is not str or not value or _utf8_size(value) > limit
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
        _fail(f"cargo_compiler_artifact_{field}_invalid", line)
    return value

def _texts(
    value: Any, field: str, line: int | None, nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        _fail(f"cargo_compiler_artifact_{field}_invalid", line)
    return sorted({_text(item, field, line) for item in value})

def _paths(value: Any, field: str, line: int | None) -> list[str]:
    if not isinstance(value, list) or not value:
        _fail(f"cargo_compiler_artifact_{field}_invalid", line)
    return sorted({_path(item, field, line) for item in value})

def _path(value: Any, field: str, line: int | None) -> str:
    raw = _text(value, field, line, 4096).replace("\\", "/")
    drive = _DRIVE_PATH.fullmatch(raw)
    if drive is not None:
        parts = drive.group("tail").split("/")
        if any(":" in part for part in parts):
            _fail(f"cargo_compiler_artifact_{field}_invalid", line)
        prefix = drive.group("drive").upper() + ":/"
    elif raw.startswith("/") and not raw.startswith("//"):
        parts, prefix = raw[1:].split("/"), "/"
    else:
        _fail(f"cargo_compiler_artifact_{field}_not_absolute", line)
    if any(not part or part in {".", ".."} for part in parts):
        _fail(f"cargo_compiler_artifact_{field}_invalid", line)
    return prefix + "/".join(parts)


def _ordered_unique(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ): value for value in values}
    return [keyed[key] for key in sorted(keyed)]


def _evidence(artifacts: list[dict[str, Any]], source_sha: str) -> dict[str, Any]:
    core = {
        "schema_version": CARGO_COMPILER_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
        "artifact_count": len(artifacts), "artifacts": artifacts,
        "artifact_set_sha256": content_sha256(artifacts),
        "build_finished_success": True, "source_sha256": source_sha,
        "interface_closure": False, "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return {**core, "content_sha256": content_sha256(core)}


def _utf8_size(value: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise CargoCompilerArtifactEvidenceError(
            "cargo_compiler_artifact_unicode_invalid"
        ) from error


def _fail(code: str, line: int | None = None) -> None:
    raise CargoCompilerArtifactEvidenceError(code, line)
