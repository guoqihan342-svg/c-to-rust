from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import PurePosixPath
import posixpath
import re
from typing import Any
import unicodedata

from .artifacts import content_sha256
from .cargo_output_limits import (
    MAX_CARGO_JSON_LINE_BYTES as _MAX_CARGO_JSON_LINE_BYTES,
    MAX_CARGO_STREAM_BYTES,
)
from .native_link_trace_json import (
    JsonObjectRequiredError, StrictJsonError, optional_json_object,
    required_json_object, trusted_linker_stdout,
)

NATIVE_LINK_TRACE_SCHEMA_VERSION = 2
MAX_CARGO_LINKER_TRACE_BYTES = MAX_CARGO_STREAM_BYTES
MAX_CARGO_JSON_LINE_BYTES = _MAX_CARGO_JSON_LINE_BYTES
MAX_LINKER_TRACE_LINE_BYTES = 4 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:[^/]*\Z", re.ASCII)
_ARCHIVE_ENTRY = re.compile(
    r"(?P<path>/[^\r\n]*\.a)\((?P<member>[^()\r\n]+)\)\Z"
)
_ALLOWED_ROOTS = (
    ("/", "usr"),
    ("/", "lib"),
    ("/", "lib64"),
    ("/", "toolchain"),
    ("/", "runtime", "target"),
    ("/", "workspace", "target"),
)
_TOP_KEYS = {
    "schema_version", "diagnostic_count", "entries", "entry_set_sha256",
    "source_sha256", "semantic_gate",
}

class CargoLinkerTraceError(ValueError):
    def __init__(self, code: str, line_number: int | None = None) -> None:
        detail = code if line_number is None else f"{code}:line:{line_number}"
        super().__init__(detail)
        self.code = code
        self.line_number = line_number

def parse_cargo_linker_trace(data: bytes) -> dict[str, Any]:
    """Parse raw Cargo JSON stdout into private, non-semantic link evidence."""
    raw, text = _decode(data)
    entries: list[dict[str, Any]] = []
    diagnostic_count = 0
    build_finished = False
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        if _utf8_size(line, "cargo_linker_trace_json_unicode_invalid") \
                > MAX_CARGO_JSON_LINE_BYTES:
            _fail("cargo_linker_trace_json_line_limit_exceeded", line_number)
        if build_finished:
            event = optional_json_object(line)
            if event is not None and event.get("reason") == "build-finished":
                _fail("cargo_linker_trace_multiple_build_finished", line_number)
            continue
        event = _required_json_object(line, line_number)
        if event.get("reason") == "build-finished":
            if event.get("success") is not True:
                _fail("cargo_linker_trace_build_failed", line_number)
            build_finished = True
            continue
        body = trusted_linker_stdout(event)
        if body is None:
            continue
        parsed = _parse_trace_body(body, line_number)
        first_ordinal = len(entries)
        entries.extend(
            {
                "ordinal": first_ordinal + offset,
                "diagnostic_ordinal": diagnostic_count,
                "link_ordinal": offset,
                **item,
            }
            for offset, item in enumerate(parsed)
        )
        diagnostic_count += 1
    if not build_finished:
        _fail("cargo_linker_trace_build_finished_missing")
    if diagnostic_count == 0:
        _fail("cargo_linker_trace_trusted_diagnostic_missing")
    payload = {
        "schema_version": NATIVE_LINK_TRACE_SCHEMA_VERSION,
        "diagnostic_count": diagnostic_count,
        "entries": entries,
        "entry_set_sha256": content_sha256(entries),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "semantic_gate": False,
    }
    return _validate_schema(payload)

def validate_cargo_linker_trace(
    value: Mapping[str, Any], source: bytes | None = None,
) -> dict[str, Any]:
    """Validate the canonical schema and optionally reparse its raw source."""
    normalized = _validate_schema(value)
    if source is not None and normalized != parse_cargo_linker_trace(source):
        _fail("cargo_linker_trace_source_reparse_drift")
    return normalized

def _decode(data: bytes) -> tuple[bytes, str]:
    if not isinstance(data, bytes):
        raise TypeError("Cargo linker trace input must be bytes")
    if len(data) > MAX_CARGO_LINKER_TRACE_BYTES:
        _fail("cargo_linker_trace_input_limit_exceeded")
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CargoLinkerTraceError(
            "cargo_linker_trace_input_not_utf8"
        ) from error

def _required_json_object(line: str, line_number: int) -> dict[str, Any]:
    try:
        return required_json_object(line)
    except JsonObjectRequiredError:
        _fail("cargo_linker_trace_json_object_required", line_number)
    except (json.JSONDecodeError, StrictJsonError) as error:
        raise CargoLinkerTraceError(
            "cargo_linker_trace_json_invalid", line_number,
        ) from error

def _parse_trace_body(body: str, line_number: int) -> list[dict[str, Any]]:
    if not body:
        _fail("cargo_linker_trace_body_empty", line_number)
    if any(
        unicodedata.category(character) == "Cc"
        and character not in "\r\n"
        for character in body
    ):
        _fail("cargo_linker_trace_control_character", line_number)
    if "\r" in body.replace("\r\n", ""):
        _fail("cargo_linker_trace_control_character", line_number)
    normalized = body.replace("\r\n", "\n")
    trace_lines = normalized.split("\n")
    if trace_lines and trace_lines[-1] == "":
        trace_lines.pop()
    if not trace_lines or any(not item for item in trace_lines):
        _fail("cargo_linker_trace_body_empty", line_number)
    result = []
    for trace_line in trace_lines:
        if _utf8_size(
            trace_line, "cargo_linker_trace_path_unicode_invalid",
        ) > MAX_LINKER_TRACE_LINE_BYTES:
            _fail("cargo_linker_trace_line_limit_exceeded", line_number)
        result.append(_parse_trace_line(trace_line, line_number))
    return result

def _parse_trace_line(value: str, line_number: int | None) -> dict[str, Any]:
    archive = _ARCHIVE_ENTRY.fullmatch(value)
    if ".a(" in value and archive is None:
        _fail("cargo_linker_trace_archive_member_invalid", line_number)
    if archive is None:
        return {"path": _guest_path(value, line_number)}
    path = _guest_path(archive.group("path"), line_number)
    member = _archive_member(archive.group("member"), line_number)
    return {"path": path, "archive_member": member}

def _guest_path(value: str, line_number: int | None) -> str:
    if (
        not value or "\\" in value
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
        _fail("cargo_linker_trace_guest_path_invalid", line_number)
    _utf8_size(value, "cargo_linker_trace_path_unicode_invalid")
    normalized = posixpath.normpath(value)
    path = PurePosixPath(normalized)
    parts = path.parts
    if (
        not value.startswith("/") or value.startswith("//")
        or not path.is_absolute() or path.as_posix() != normalized
        or normalized.startswith("//")
        or any(_WINDOWS_DRIVE.fullmatch(part) for part in parts)
    ):
        _fail("cargo_linker_trace_guest_path_invalid", line_number)
    if not any(parts[:len(root)] == root for root in _ALLOWED_ROOTS):
        _fail("cargo_linker_trace_guest_root_forbidden", line_number)
    return normalized

def _archive_member(value: str, line_number: int | None) -> str:
    if (
        not value or "\\" in value
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
        _fail("cargo_linker_trace_archive_member_invalid", line_number)
    _utf8_size(value, "cargo_linker_trace_path_unicode_invalid")
    member = PurePosixPath(value)
    if (
        value == "." or member.is_absolute() or member.as_posix() != value
        or ".." in member.parts or value.startswith("~")
        or any(_WINDOWS_DRIVE.fullmatch(part) for part in member.parts)
    ):
        _fail("cargo_linker_trace_archive_member_invalid", line_number)
    return value

def _validate_schema(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        _fail("cargo_linker_trace_schema_invalid")
    raw_entries = value.get("entries")
    count = value.get("diagnostic_count")
    if not isinstance(raw_entries, list) or not raw_entries:
        _fail("cargo_linker_trace_entries_invalid")
    entries = []
    previous_diagnostic = -1
    previous_link = -1
    for ordinal, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, Mapping):
            _fail("cargo_linker_trace_entry_schema_invalid")
        keys = {"ordinal", "diagnostic_ordinal", "link_ordinal", "path"}
        if "archive_member" in raw_entry:
            keys.add("archive_member")
        diagnostic = raw_entry.get("diagnostic_ordinal")
        link = raw_entry.get("link_ordinal")
        if (
            set(raw_entry) != keys or raw_entry.get("ordinal") != ordinal
            or type(diagnostic) is not int or diagnostic < 0
            or type(link) is not int or link < 0
            or (
                diagnostic == previous_diagnostic
                and link != previous_link + 1
            )
            or (
                diagnostic != previous_diagnostic
                and (diagnostic != previous_diagnostic + 1 or link != 0)
            )
        ):
            _fail("cargo_linker_trace_entry_schema_invalid")
        path = raw_entry.get("path")
        member = raw_entry.get("archive_member")
        if not isinstance(path, str) or (member is not None and not isinstance(member, str)):
            _fail("cargo_linker_trace_entry_schema_invalid")
        encoded = path if member is None else f"{path}({member})"
        expected = {
            "ordinal": ordinal,
            "diagnostic_ordinal": diagnostic,
            "link_ordinal": link,
            **_parse_trace_line(encoded, None),
        }
        if dict(raw_entry) != expected:
            _fail("cargo_linker_trace_entry_schema_invalid")
        entries.append(expected)
        previous_diagnostic = diagnostic
        previous_link = link
    if (
        value.get("schema_version") != NATIVE_LINK_TRACE_SCHEMA_VERSION
        or type(count) is not int or count != previous_diagnostic + 1
        or value.get("semantic_gate") is not False
        or _SHA256.fullmatch(str(value.get("source_sha256"))) is None
    ):
        _fail("cargo_linker_trace_summary_invalid")
    if (
        _SHA256.fullmatch(str(value.get("entry_set_sha256"))) is None
        or value.get("entry_set_sha256") != content_sha256(entries)
    ):
        _fail("cargo_linker_trace_entry_set_sha256_drift")
    return {
        "schema_version": NATIVE_LINK_TRACE_SCHEMA_VERSION,
        "diagnostic_count": count,
        "entries": entries,
        "entry_set_sha256": value["entry_set_sha256"],
        "source_sha256": value["source_sha256"],
        "semantic_gate": False,
    }

def _utf8_size(value: str, code: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise CargoLinkerTraceError(code) from error

def _fail(code: str, line_number: int | None = None) -> None:
    raise CargoLinkerTraceError(code, line_number)

__all__ = [
    "CargoLinkerTraceError", "MAX_CARGO_JSON_LINE_BYTES",
    "MAX_CARGO_LINKER_TRACE_BYTES", "MAX_LINKER_TRACE_LINE_BYTES",
    "NATIVE_LINK_TRACE_SCHEMA_VERSION", "parse_cargo_linker_trace",
    "validate_cargo_linker_trace",
]
