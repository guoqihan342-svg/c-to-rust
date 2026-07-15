from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .clang_record_layout_fact_evidence import (
    MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES,
    ClangRecordLayoutFactEvidenceError,
    parse_clang_record_layout_fact_evidence,
)


_MARKER = b"*** Dumping AST Record Layout"
_HEADER = re.compile(
    rb"^[ \t]*0[ \t]*\|[ \t]*struct[ \t]+"
    rb"(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*\r?\n?$"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}


def parse_selected_clang_record_layout_fact_evidence(
    stdout: bytes,
    stderr: bytes,
    toolchain_sha256: str,
    target_context_sha256: str,
    interface_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep only source-bound AST records before parsing noisy Clang layouts."""
    if type(stdout) is not bytes or type(stderr) is not bytes:
        raise TypeError("Clang record-layout stdout and stderr must be bytes")
    if len(stdout) + len(stderr) > MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES:
        _fail("clang_record_layout_input_limit")
    selected = _selected_records(interface_evidence)
    names = {item["name"] for item in selected}
    filtered_stdout, stdout_names = _filter_stream(stdout, names)
    filtered_stderr, stderr_names = _filter_stream(stderr, names)
    parsed = parse_clang_record_layout_fact_evidence(
        filtered_stdout,
        filtered_stderr,
        toolchain_sha256,
        target_context_sha256,
    )
    observed = stdout_names | stderr_names
    blockers = list(parsed["blockers"])
    if not selected:
        blockers.append(_block("clang_record_layout_selected_record_set_empty"))
    for item in selected:
        if item["complete"] is not True:
            blockers.append(_block(
                "clang_record_layout_selected_record_incomplete", item["name"],
            ))
        if item["name"] not in observed:
            blockers.append(_block(
                "clang_record_layout_selected_record_missing", item["name"],
            ))
    blockers = _canonical_blockers(blockers)
    records = parsed["records"]
    if {item["name"] for item in records} != names:
        blockers.append(_block("clang_record_layout_selected_record_set_mismatch"))
        blockers = _canonical_blockers(blockers)
    selection = {
        "interface_evidence_sha256": interface_evidence["evidence_sha256"],
        "records": selected,
    }
    selection["selection_sha256"] = content_sha256(selection)
    core = {
        "schema_version": 1,
        "artifact_kind": "selected-clang-record-layout-fact-evidence",
        "status": "blocked" if blockers else "facts-ready",
        "raw_stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "raw_stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "raw_stream_set_sha256": _stream_set_sha256(stdout, stderr),
        "toolchain_sha256": toolchain_sha256,
        "target_context_sha256": target_context_sha256,
        "selection": selection,
        "filtered_layout_evidence": parsed,
        "record_count": len(records),
        "records": records,
        "blockers": blockers,
        "section_closure": False,
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return {**core, "facts_sha256": content_sha256(core)}


def validate_selected_clang_record_layout_fact_evidence(
    value: Any,
    stdout: bytes,
    stderr: bytes,
    toolchain_sha256: str,
    target_context_sha256: str,
    interface_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("clang_record_layout_selected_evidence_schema")
    expected = parse_selected_clang_record_layout_fact_evidence(
        stdout,
        stderr,
        toolchain_sha256,
        target_context_sha256,
        interface_evidence,
    )
    if dict(value) != expected:
        _fail("clang_record_layout_selected_source_reparse_drift")
    return expected


def _selected_records(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, Mapping):
        _fail("clang_interface_evidence_required")
    stored = value.get("evidence_sha256")
    payload = {key: item for key, item in value.items() if key != "evidence_sha256"}
    records = value.get("records")
    if (
        not isinstance(stored, str)
        or _SHA256.fullmatch(stored) is None
        or _compact_sha256(payload) != stored
        or value.get("section_closure") is not False
        or value.get("semantic_gate") is not False
        or value.get("translation_coverage_numerator") != 0
        or not isinstance(records, list)
    ):
        _fail("clang_interface_evidence_invalid")
    selected = []
    for record in records:
        if not isinstance(record, Mapping):
            _fail("clang_interface_record_invalid")
        name = record.get("name")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
            or record.get("tag") != "struct"
            or type(record.get("complete")) is not bool
            or not isinstance(record.get("source_spans"), list)
            or not record["source_spans"]
        ):
            _fail("clang_interface_record_invalid")
        selected.append({
            "name": name,
            "complete": record["complete"],
            "interface_record_sha256": content_sha256(record),
        })
    if selected != sorted(selected, key=lambda item: item["name"]):
        _fail("clang_interface_record_order_invalid")
    if len({item["name"] for item in selected}) != len(selected):
        _fail("clang_interface_record_duplicate")
    return selected


def _filter_stream(data: bytes, selected: set[str]) -> tuple[bytes, set[str]]:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ClangRecordLayoutFactEvidenceError(
            "clang_record_layout_input_not_utf8"
        ) from error
    lines = data.splitlines(keepends=True)
    output = bytearray()
    observed: set[str] = set()
    index = 0
    while index < len(lines):
        if lines[index].rstrip(b"\r\n").strip() != _MARKER:
            index += 1
            continue
        end = index + 1
        while end < len(lines) and lines[end].rstrip(b"\r\n").strip() != _MARKER:
            end += 1
        name = _block_name(lines[index + 1:end])
        if name in selected:
            output.extend(b"".join(lines[index:end]))
            observed.add(name)
        index = end
    return bytes(output), observed


def _block_name(lines: list[bytes]) -> str | None:
    for line in lines:
        if not line.strip():
            continue
        match = _HEADER.fullmatch(line)
        return match.group("name").decode("ascii") if match else None
    return None


def _block(code: str, record: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "stream": None,
        "line_number": None,
        "record_name": record,
        "field_ordinal": None,
    }


def _canonical_blockers(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        {content_sha256(item): item for item in values}.values(),
        key=lambda item: (
            str(item.get("code")), str(item.get("stream") or ""),
            int(item.get("line_number") or -1), str(item.get("record_name") or ""),
            int(item.get("field_ordinal") if item.get("field_ordinal") is not None else -1),
        ),
    )


def _stream_set_sha256(stdout: bytes, stderr: bytes) -> str:
    digest = hashlib.sha256(b"selected-clang-record-layout-raw-v1\0")
    for label, data in ((b"stdout\0", stdout), (b"stderr\0", stderr)):
        digest.update(label + len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def _compact_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _fail(code: str) -> None:
    raise ClangRecordLayoutFactEvidenceError(code)


__all__ = [
    "parse_selected_clang_record_layout_fact_evidence",
    "validate_selected_clang_record_layout_fact_evidence",
]
