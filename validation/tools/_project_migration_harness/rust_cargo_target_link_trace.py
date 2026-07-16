from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .cargo_compiler_artifact_evidence import (
    parse_cargo_compiler_artifact_evidence,
)
from .native_link_trace import parse_cargo_linker_trace
from .native_link_trace_json import (
    StrictJsonError, required_json_object, trusted_linker_stdout,
)


SCHEMA_VERSION = 1
_PACKAGE_SUFFIX = re.compile(
    r"(?P<name>[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})@"
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.+_-]{0,127})\Z",
    re.ASCII,
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TOP_KEYS = {
    "schema_version", "diagnostic_count", "diagnostics",
    "diagnostic_set_sha256", "source_sha256", "semantic_gate",
    "translation_coverage_numerator",
}
_DIAGNOSTIC_KEYS = {"package", "target", "entries", "entry_set_sha256"}
_PACKAGE_KEYS = {"name", "version", "package_id_sha256"}
_TARGET_KEYS = {"name", "kind", "crate_types"}


def parse_rust_cargo_target_link_trace(data: bytes) -> dict[str, Any]:
    compiler = parse_cargo_compiler_artifact_evidence(data)
    trace = parse_cargo_linker_trace(data)
    events = _linker_events(data)
    if len(events) != trace["diagnostic_count"]:
        raise ValueError("rust_cargo_target_link_trace_count_drifted")
    diagnostics = []
    for ordinal, event in enumerate(events):
        artifact = _bound_artifact(event, compiler["artifacts"])
        entries = [_entry(item) for item in trace["entries"]
                   if item["diagnostic_ordinal"] == ordinal]
        diagnostics.append({
            "package": _package(artifact["package_id"]),
            "target": {
                "name": artifact["target"]["name"],
                "kind": artifact["target"]["kind"],
                "crate_types": artifact["target"]["crate_types"],
            },
            "entries": entries, "entry_set_sha256": content_sha256(entries),
        })
    diagnostics = sorted(diagnostics, key=canonical_json_bytes)
    identities = [_identity(item) for item in diagnostics]
    if len(identities) != len(set(identities)):
        raise ValueError("rust_cargo_target_link_trace_target_duplicate")
    result = {
        "schema_version": SCHEMA_VERSION,
        "diagnostic_count": len(diagnostics), "diagnostics": diagnostics,
        "diagnostic_set_sha256": content_sha256(diagnostics),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "semantic_gate": False, "translation_coverage_numerator": 0,
    }
    return validate_rust_cargo_target_link_trace(result)


def validate_rust_cargo_target_link_trace(
    value: Any, source: bytes | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("rust_cargo_target_link_trace_schema_invalid")
    diagnostics = value.get("diagnostics")
    if not isinstance(diagnostics, list) or not diagnostics:
        raise ValueError("rust_cargo_target_link_trace_diagnostics_invalid")
    normalized = [_validate_diagnostic(item) for item in diagnostics]
    identities = [_identity(item) for item in normalized]
    if normalized != sorted(normalized, key=canonical_json_bytes) \
            or len(identities) != len(set(identities)):
        raise ValueError("rust_cargo_target_link_trace_not_canonical")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("diagnostic_count") != len(normalized)
        or value.get("diagnostic_set_sha256") != content_sha256(normalized)
        or _SHA256.fullmatch(str(value.get("source_sha256"))) is None
        or value.get("semantic_gate") is not False
        or value.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("rust_cargo_target_link_trace_invalid")
    result = dict(value)
    if source is not None and result != parse_rust_cargo_target_link_trace(source):
        raise ValueError("rust_cargo_target_link_trace_source_reparse_drift")
    return result


def _linker_events(data: bytes) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8")
    except (AttributeError, UnicodeDecodeError) as error:
        raise ValueError("rust_cargo_target_link_trace_source_invalid") from error
    result = []
    for raw_line in text.splitlines():
        try:
            event = required_json_object(raw_line)
        except (json.JSONDecodeError, StrictJsonError, ValueError) as error:
            raise ValueError("rust_cargo_target_link_trace_json_invalid") from error
        if event.get("reason") == "build-finished":
            break
        if trusted_linker_stdout(event) is not None:
            result.append(event)
    return result


def _bound_artifact(
    event: Mapping[str, Any], artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    target = event.get("target")
    if not isinstance(target, Mapping):
        raise ValueError("rust_cargo_target_link_trace_target_invalid")
    matches = [item for item in artifacts if (
        item["package_id"] == event.get("package_id")
        and item["target"]["name"] == target.get("name")
        and item["target"]["kind"] == sorted(set(target.get("kind", [])))
        and item["target"]["crate_types"]
        == sorted(set(target.get("crate_types", [])))
    )]
    if len(matches) != 1:
        raise ValueError("rust_cargo_target_link_trace_artifact_binding_invalid")
    return matches[0]


def _entry(value: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "link_ordinal": value["link_ordinal"],
        "guest_path_sha256": hashlib.sha256(
            value["path"].encode("utf-8"),
        ).hexdigest(),
    }
    if "archive_member" in value:
        result["archive_member_sha256"] = hashlib.sha256(
            value["archive_member"].encode("utf-8"),
        ).hexdigest()
    return result


def _validate_diagnostic(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _DIAGNOSTIC_KEYS:
        raise ValueError("rust_cargo_target_link_trace_diagnostic_invalid")
    package, target = value.get("package"), value.get("target")
    if not isinstance(package, Mapping) or set(package) != _PACKAGE_KEYS \
            or not _text(package.get("name")) \
            or not _text(package.get("version")) \
            or _SHA256.fullmatch(str(package.get("package_id_sha256"))) is None:
        raise ValueError("rust_cargo_target_link_trace_package_invalid")
    if not isinstance(target, Mapping) or set(target) != _TARGET_KEYS \
            or not _text(target.get("name")) \
            or not _texts(target.get("kind")) \
            or not _texts(target.get("crate_types")):
        raise ValueError("rust_cargo_target_link_trace_target_invalid")
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("rust_cargo_target_link_trace_entries_invalid")
    normalized = [_validate_entry(item, ordinal)
                  for ordinal, item in enumerate(entries)]
    if value.get("entry_set_sha256") != content_sha256(normalized):
        raise ValueError("rust_cargo_target_link_trace_entry_hash_drifted")
    result = {"package": dict(package), "target": dict(target),
              "entries": normalized, "entry_set_sha256": value["entry_set_sha256"]}
    if dict(value) != result:
        raise ValueError("rust_cargo_target_link_trace_diagnostic_not_canonical")
    return result


def _validate_entry(value: Any, ordinal: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) not in (
        {"link_ordinal", "guest_path_sha256"},
        {"link_ordinal", "guest_path_sha256", "archive_member_sha256"},
    ) or value.get("link_ordinal") != ordinal \
            or _SHA256.fullmatch(str(value.get("guest_path_sha256"))) is None \
            or ("archive_member_sha256" in value and _SHA256.fullmatch(
                str(value.get("archive_member_sha256")),
            ) is None):
        raise ValueError("rust_cargo_target_link_trace_entry_invalid")
    return dict(value)


def _package(package_id: str) -> dict[str, str]:
    match = _PACKAGE_SUFFIX.search(package_id)
    if match is None:
        raise ValueError("rust_cargo_target_link_trace_package_id_invalid")
    return {
        "name": match.group("name"), "version": match.group("version"),
        "package_id_sha256": hashlib.sha256(package_id.encode("utf-8")).hexdigest(),
    }


def _identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(value["package"]["name"]), str(value["package"]["version"]),
            str(value["target"]["name"]))


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 256


def _texts(value: Any) -> bool:
    return isinstance(value, list) and bool(value) \
        and value == sorted(set(value)) and all(_text(item) for item in value)


__all__ = [
    "SCHEMA_VERSION", "parse_rust_cargo_target_link_trace",
    "validate_rust_cargo_target_link_trace",
]
