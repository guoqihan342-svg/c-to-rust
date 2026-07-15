from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any
from .artifacts import content_sha256

CLANG_RECORD_LAYOUT_FACT_EVIDENCE_SCHEMA_VERSION = 1
MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES = 2 * 1024 * 1024
MAX_CLANG_RECORD_LAYOUT_LINE_BYTES = 16 * 1024
MAX_CLANG_RECORD_LAYOUT_RECORDS = 1024
MAX_CLANG_RECORD_LAYOUT_FIELDS = 4096
_MAX_LAYOUT_BYTES = 1 << 60
_MARKER = "*** Dumping AST Record Layout"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
_HEADER = re.compile(r"(struct|union)[ \t]+(.+)\Z", re.ASCII)
_LAYOUT = re.compile(r"^[ \t]*(?P<offset>[0-9]+(?::(?:[0-9]+(?:-[0-9]+)?|-))?)"
                     r"[ \t]*\|(?P<body>.*)$", re.ASCII)
_SUMMARY = re.compile(r"^[ \t]*\|[ \t]*\[(?P<meta>[^\]]*)\][ \t]*$", re.ASCII)
_FIELD = re.compile(r"(?P<type>.+(?:[ \t]|\*))(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
                    r"(?P<arrays>(?:[ \t]*\[[^\[\]]*\])*)\Z", re.ASCII)
_ANONYMOUS = re.compile(r"(?:\(anonymous\b|\bunnamed\b)", re.IGNORECASE)
_ANONYMOUS_FIELD = re.compile(r"(?:struct|union)[ \t]+[A-Za-z_][A-Za-z0-9_]*\Z",
                              re.ASCII)
_CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}
class ClangRecordLayoutFactEvidenceError(ValueError):
    def __init__(self, code: str, stream: str | None = None,
                 line_number: int | None = None) -> None:
        suffix = "" if stream is None else f":{stream}"
        suffix += "" if line_number is None else f":line:{line_number}"
        super().__init__(code + suffix)
        self.code, self.stream, self.line_number = code, stream, line_number
def parse_clang_record_layout_fact_evidence(
    stdout: bytes, stderr: bytes, toolchain_sha256: str, target_context_sha256: str,
) -> dict[str, Any]:
    if type(stdout) is not bytes or type(stderr) is not bytes:
        raise TypeError("Clang record-layout stdout and stderr must be bytes")
    if len(stdout) + len(stderr) > MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES:
        _fail("clang_record_layout_input_limit")
    toolchain = _sha(toolchain_sha256, "toolchain")
    target = _sha(target_context_sha256, "target_context")
    streams = [("stdout", _lines(stdout, "stdout")),
               ("stderr", _lines(stderr, "stderr"))]
    records, blockers = _scan(streams)
    core = {
        "schema_version": CLANG_RECORD_LAYOUT_FACT_EVIDENCE_SCHEMA_VERSION,
        "artifact_kind": "clang-record-layout-fact-evidence",
        "status": "blocked" if blockers else "facts-ready",
        "raw_sha256": _raw_sha(stdout, stderr),
        "toolchain_sha256": toolchain,
        "target_context_sha256": target,
        "record_count": len(records), "records": records,
        "blockers": blockers, "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return {**core, "facts_sha256": content_sha256(core)}
def validate_clang_record_layout_fact_evidence(
    value: Any, stdout: bytes, stderr: bytes, toolchain_sha256: str,
    target_context_sha256: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("clang_record_layout_evidence_schema")
    expected = parse_clang_record_layout_fact_evidence(
        stdout, stderr, toolchain_sha256, target_context_sha256,
    )
    if dict(value) != expected:
        _fail("clang_record_layout_source_reparse_drift")
    return expected
def _lines(data: bytes, stream: str) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ClangRecordLayoutFactEvidenceError(
            "clang_record_layout_input_not_utf8", stream,
        ) from error
    lines = []
    for number, raw in enumerate(text.split("\n"), 1):
        line = raw[:-1] if raw.endswith("\r") else raw
        if "\r" in line or len(line.encode("utf-8")) > MAX_CLANG_RECORD_LAYOUT_LINE_BYTES:
            _fail("clang_record_layout_line_invalid_or_too_long", stream, number)
        lines.append(line)
    return lines
def _scan(
    streams: list[tuple[str, list[str]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    found: list[tuple[dict[str, Any], str, int]] = []
    blockers: list[dict[str, Any]] = []
    count = 0
    for stream, lines in streams:
        index = 0
        while index < len(lines):
            if lines[index].strip() != _MARKER:
                index += 1
                continue
            count += 1
            if count > MAX_CLANG_RECORD_LAYOUT_RECORDS:
                _fail("clang_record_layout_record_limit", stream, index + 1)
            marker_line = index + 1
            index += 1
            body: list[tuple[int, str]] = []
            summary: tuple[int, str] | None = None
            while index < len(lines) and lines[index].strip() != _MARKER:
                match = _SUMMARY.fullmatch(lines[index])
                if match is not None:
                    summary = (index + 1, match.group("meta"))
                    index += 1
                    break
                body.append((index + 1, lines[index]))
                index += 1
            record, local = _parse_block(stream, marker_line, body, summary)
            blockers.extend(local)
            if record is not None:
                found.append((record, stream, marker_line))
    if count == 0:
        blockers.append(_block("clang_record_layout_block_missing"))
    counts: dict[tuple[str, str], int] = {}
    for record, _, _ in found:
        key = record["kind"], record["name"]
        counts[key] = counts.get(key, 0) + 1
    for record, stream, line in found:
        if counts[(record["kind"], record["name"])] > 1:
            blockers.append(_block(
                "clang_record_layout_duplicate_record", stream, line, record["name"],
            ))
    records = [record for record, _, _ in found
               if counts[(record["kind"], record["name"])] == 1]
    records.sort(key=lambda item: (item["kind"], item["name"]))
    return records, _sort_blockers(blockers)
def _parse_block(
    stream: str, marker_line: int, body: list[tuple[int, str]],
    summary: tuple[int, str] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    rows = [(line, text) for line, text in body if text.strip()]
    if not rows:
        return None, [_block("clang_record_layout_header_unrecognized",
                             stream, marker_line)]
    header_line, header_text = rows[0]
    layout = _LAYOUT.fullmatch(header_text)
    if layout is None or layout.group("offset") != "0" or "\t" in layout.group("body"):
        return None, [_block("clang_record_layout_header_unrecognized",
                             stream, header_line)]
    header_body = layout.group("body")
    header_indent = len(header_body) - len(header_body.lstrip(" "))
    header = _HEADER.fullmatch(header_body.strip())
    if header is None:
        return None, [_block("clang_record_layout_header_unrecognized",
                             stream, header_line)]
    kind, name = header.groups()
    if _ANONYMOUS.search(name):
        return None, [_block("clang_record_layout_anonymous_record",
                             stream, header_line)]
    if _IDENTIFIER.fullmatch(name) is None:
        return None, [_block("clang_record_layout_header_unrecognized",
                             stream, header_line)]
    dimensions, dimension_code = _dimensions(summary)
    blockers = [] if dimension_code is None else [_block(
        dimension_code, stream, summary[0] if summary else marker_line, name,
    )]
    invalid = dimension_code is not None
    fields: list[dict[str, Any]] = []
    ordinal = 0
    for line, text in rows[1:]:
        match = _LAYOUT.fullmatch(text)
        if match is None or "\t" in match.group("body"):
            blockers.append(_block(
                "clang_record_layout_field_unparseable", stream, line, name, ordinal,
            ))
            invalid = True
            continue
        field_body = match.group("body")
        indent = len(field_body) - len(field_body.lstrip(" "))
        content = field_body.strip()
        if indent > header_indent + 2:
            code = (
                "clang_record_layout_bitfield_unsupported"
                if ":" in match.group("offset") else
                "clang_record_layout_anonymous_field"
                if _ANONYMOUS.search(content) else
                "clang_record_layout_flexible_array_unsupported"
                if re.search(r"\[[ \t]*\][ \t]*\Z", content) else None
            )
            if code:
                blockers.append(_block(code, stream, line, name))
                invalid = True
            continue
        field_ordinal = ordinal
        ordinal += 1
        if ordinal > MAX_CLANG_RECORD_LAYOUT_FIELDS:
            _fail("clang_record_layout_field_limit", stream, line)
        fact, code = (
            _field(match.group("offset"), content, field_ordinal)
            if indent == header_indent + 2
            else (None, "clang_record_layout_field_unparseable")
        )
        if code:
            blockers.append(_block(code, stream, line, name, field_ordinal))
            invalid = True
        elif fact:
            fields.append(fact)
    if len({field["name"] for field in fields}) != len(fields):
        blockers.append(_block(
            "clang_record_layout_field_unparseable", stream, header_line, name,
        ))
        invalid = True
    if dimensions:
        for field in fields:
            if field["offset_bits"] >= dimensions[0]:
                blockers.append(_block(
                    "clang_record_layout_field_offset_out_of_bounds", stream,
                    header_line, name, field["ordinal"],
                ))
                invalid = True
    if kind == "union":
        blockers.append(_block(
            "clang_record_layout_union_unsupported", stream, header_line, name,
        ))
    if invalid or dimensions is None:
        return None, blockers
    return {
        "name": name, "kind": kind, "size_bits": dimensions[0],
        "align_bits": dimensions[1], "fields": fields,
    }, blockers
def _field(
    offset: str, content: str, ordinal: int,
) -> tuple[dict[str, Any] | None, str | None]:
    if ":" in offset:
        return None, "clang_record_layout_bitfield_unsupported"
    if _ANONYMOUS.search(content) or _ANONYMOUS_FIELD.fullmatch(content):
        return None, "clang_record_layout_anonymous_field"
    if any(ord(character) < 32 for character in content):
        return None, "clang_record_layout_field_unparseable"
    match = _FIELD.fullmatch(content)
    if match is None:
        return None, "clang_record_layout_field_unparseable"
    arrays = re.findall(r"\[[ \t]*([^\[\]]*?)[ \t]*\]", match.group("arrays"))
    if any(not dimension for dimension in arrays):
        return None, "clang_record_layout_flexible_array_unsupported"
    if any(not dimension.isascii() or not dimension.isdecimal() for dimension in arrays):
        return None, "clang_record_layout_field_unparseable"
    type_text = " ".join(match.group("type").split())
    type_text += "".join(f"[{int(dimension)}]" for dimension in arrays)
    offset_bytes = _number(offset)
    if not type_text or len(type_text.encode("utf-8")) > 4096 or offset_bytes is None:
        return None, "clang_record_layout_field_unparseable"
    return ({"ordinal": ordinal, "name": match.group("name"),
             "type_text": type_text, "offset_bits": offset_bytes * 8}, None)
def _dimensions(
    summary: tuple[int, str] | None,
) -> tuple[tuple[int, int] | None, str | None]:
    if summary is None:
        return None, "clang_record_layout_size_align_missing"
    values: dict[str, list[str]] = {"sizeof": [], "align": []}
    pattern = (r"(?<![A-Za-z0-9_])(sizeof|align)[ \t]*=[ \t]*([0-9]+)"
               r"(?![A-Za-z0-9_])")
    for key, raw in re.findall(pattern, summary[1], re.ASCII):
        values[key].append(raw)
    if any(len(values[key]) != 1 for key in values):
        return None, "clang_record_layout_size_align_missing"
    size, align = _number(values["sizeof"][0]), _number(values["align"][0])
    if (
        size is None or align is None or size <= 0 or align <= 0
        or align & (align - 1) or size % align
    ):
        return None, "clang_record_layout_dimensions_invalid"
    return (size * 8, align * 8), None
def _block(
    code: str, stream: str | None = None, line: int | None = None,
    record: str | None = None, ordinal: int | None = None,
) -> dict[str, Any]:
    return {"code": code, "stream": stream, "line_number": line,
            "record_name": record, "field_ordinal": ordinal}
def _sort_blockers(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {(
        item["code"], item["stream"] or "", item["line_number"] or -1,
        item["record_name"] or "",
        item["field_ordinal"] if item["field_ordinal"] is not None else -1,
    ): item for item in values}
    return [keyed[key] for key in sorted(keyed)]

def _raw_sha(stdout: bytes, stderr: bytes) -> str:
    digest = hashlib.sha256(b"clang-record-layout-raw-v1\0")
    for label, data in ((b"stdout\0", stdout), (b"stderr\0", stderr)):
        digest.update(label + len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()

def _number(value: str) -> int | None:
    if len(value) > 18 or not value.isascii() or not value.isdecimal():
        return None
    result = int(value)
    return result if result <= _MAX_LAYOUT_BYTES else None

def _sha(value: Any, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(f"clang_record_layout_{field}_sha256_invalid")
    return value

def _fail(code: str, stream: str | None = None,
          line: int | None = None) -> None:
    raise ClangRecordLayoutFactEvidenceError(code, stream, line)
