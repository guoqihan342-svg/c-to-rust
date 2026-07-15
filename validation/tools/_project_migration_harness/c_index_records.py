from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .c_index_lexical import IDENT, WORDS, matching, split_top_level
from .c_index_macros import span_is_unconditional


_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def global_records(scanned: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for unit in scanned:
        if not unit["function_spans_reliable"]:
            continue
        for item in unit["globals_raw"]:
            if not span_is_unconditional(
                item["start"], item["end"], unit["conditional_ranges"]
            ):
                continue
            span = unit["raw"][item["start"]:item["end"]]
            digest = hashlib.sha256(span).hexdigest()
            content, encoding = _source_content(span)
            records.append({
                "global_id": _content_id(
                    "global", unit["unit_id"], unit["sha256"], digest,
                    item["symbol"], item["linkage"],
                ),
                "unit_id": unit["unit_id"],
                "symbol": item["symbol"],
                "linkage": item["linkage"],
                "source": {
                    "path": unit["path"], "sha256": unit["sha256"],
                    "encoding": encoding,
                    "span": {
                        "byte_start": item["start"], "byte_end": item["end"],
                        "sha256": digest,
                    },
                    "content": content,
                },
            })
    return records


def function_records(
    scanned: Sequence[dict[str, Any]], global_names: set[str]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for unit in scanned:
        if not unit["function_spans_reliable"]:
            records.append(_boundary_node(unit))
            continue
        for item in unit["functions"]:
            records.append(_function_record(unit, item, global_names))
    return records


def _function_record(
    unit: Mapping[str, Any], item: Mapping[str, Any], global_names: set[str]
) -> dict[str, Any]:
    span = unit["raw"][item["start"]:item["end"]]
    digest = hashlib.sha256(span).hexdigest()
    linkage = "internal" if re.search(r"\bstatic\b", item["header"]) else "external"
    body = unit["masked"][item["open"] + 1:item["end"] - 1]
    locals_ = _declared_locals(item["header"], body, item["symbol"])
    identifiers = set(IDENT.findall(body)) - locals_
    content, encoding = _source_content(span)
    signature_span = unit["raw"][item["start"]:item["open"]]
    signature_content, signature_encoding = _source_content(signature_span)
    return {
        "node_id": _content_id(
            "function", unit["unit_id"], unit["sha256"], digest,
            str(item["start"]), linkage,
        ),
        "node_kind": "function", "unit_id": unit["unit_id"],
        "symbol": item["symbol"], "linkage": linkage,
        "direct_calls": sorted(_direct_calls(body) - locals_),
        "referenced_globals": sorted(identifiers & global_names),
        "macro_definitions": [
            dict(macro) for macro in unit["source_macros"]
            if macro["name"] in identifiers
        ],
        "source": {
            "path": unit["path"], "sha256": unit["sha256"],
            "encoding": encoding,
            "span": {
                "byte_start": item["start"], "byte_end": item["end"],
                "sha256": digest,
            },
            "content": content,
        },
        "signature": {
            "path": unit["path"], "sha256": unit["sha256"],
            "encoding": signature_encoding,
            "span": {
                "byte_start": item["start"], "byte_end": item["open"],
                "sha256": hashlib.sha256(signature_span).hexdigest(),
            },
            "content": signature_content,
        },
    }


def _boundary_node(unit: Mapping[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(unit["raw"]).hexdigest()
    content, encoding = _source_content(unit["raw"])
    return {
        "node_id": _content_id("translation_unit", unit["unit_id"], digest),
        "node_kind": "translation_unit_boundary", "unit_id": unit["unit_id"],
        "symbol": f"c2r_unit_{digest[:16]}", "linkage": "internal",
        "direct_calls": [], "referenced_globals": [],
        "source": {
            "path": unit["path"], "sha256": unit["sha256"],
            "encoding": encoding,
            "span": {
                "byte_start": 0, "byte_end": len(unit["raw"]), "sha256": digest,
            },
            "content": content,
        },
    }


def _declared_locals(header: str, body: str, function_name: str) -> set[str]:
    result: set[str] = set()
    marker = re.search(rf"\b{re.escape(function_name)}\s*\(", header)
    if marker:
        opening = header.find("(", marker.start())
        closing = matching(header, opening, "(", ")")
        if closing is not None:
            for part in split_top_level(header[opening + 1:closing], ","):
                names = [name for name in IDENT.findall(part) if name not in WORDS]
                if names:
                    result.add(names[-1])
    pattern = (
        r"(?:^|[;{}])\s*(?:(?:const|volatile|signed|unsigned|short|long)\s+)*"
        r"(?:char|int|float|double|_Bool|struct\s+\w+|union\s+\w+|enum\s+\w+)"
        r"\s+\**\s*([A-Za-z_]\w*)"
    )
    result.update(re.findall(pattern, body))
    return result


def _direct_calls(body: str) -> set[str]:
    result: set[str] = set()
    for match in _CALL.finditer(body):
        name = match.group(1)
        prefix = body[:match.start()].rstrip()
        if name not in WORDS and not prefix.endswith((".", "->")):
            result.add(name)
    return result


def _source_content(span: bytes) -> tuple[str, str]:
    try:
        return span.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return span.decode("latin-1"), "latin-1-byte-map"


def _content_id(kind: str, *parts: str) -> str:
    payload = json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return f"{kind}-{hashlib.sha256(payload).hexdigest()[:24]}"


__all__ = ["function_records", "global_records"]
