"""Repository-confined lexical indexing for bounded C project migration."""
from __future__ import annotations
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from .build_facts import is_linklike
from .c_index_dependencies import (
    dependency_context as _dependency_context,
    normalize_compile_context as _normalize_compile_context,
    top_level_context as _top_level_context,
)
from .c_index_blockers import build_blocker_catalog
from .c_index_blocker_validation import validate_blocker_catalog
from .c_index_span_policy import function_spans_reliable
from .c_index_dependency_snapshot import DependencySnapshot
from .c_index_lexical import (
    IDENT as _IDENT,
    WORDS as _WORDS,
    function_name as _function_name,
    global_candidates as _global_candidates,
    mask_non_code as _mask_non_code,
    matching as _matching,
    split_top_level as _split_top_level,
)
_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 256 * 1024 * 1024
PARSER_LIMITATIONS = ["lexical_subset_without_preprocessor_or_type_analysis",
    "conditional_compilation_branches_are_not_evaluated",
    "macro_generated_definitions_and_calls_are_not_visible",
    "function_pointer_and_computed_calls_are_not_resolved",
    "global_references_are_limited_to_declarations_in_supplied_translation_units",
    "old_style_kr_function_definitions_are_not_supported",
    "recoverable_parser_boundaries_preserve_spans_without_semantic_claims"]
def index_translation_units(repo_root: str | Path,
                            translation_units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Index source-bound functions, direct calls, and declared globals."""
    requested_root = Path(repo_root)
    if is_linklike(requested_root):
        raise ValueError("repo_root must not be a link or junction")
    root = requested_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repo_root must be an existing directory")
    units = []
    dependency_snapshot = DependencySnapshot(root)
    total_source_bytes = 0
    for item in translation_units:
        unit = _validated_unit(root, item, dependency_snapshot)
        total_source_bytes += len(unit["raw"])
        if total_source_bytes > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError("translation unit total source byte limit exceeded")
        units.append(unit)
    unit_ids = [item["unit_id"] for item in units]
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("translation unit unit_id values must be unique")
    scanned: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for unit in sorted(units, key=lambda item: item["unit_id"]):
        scan = _scan_unit(unit)
        dependencies = _dependency_context(root, unit, dependency_snapshot)
        scan["blockers"].extend(dependencies["blockers"])
        scan["blockers"] = sorted(
            {tuple(sorted(item.items())): item for item in scan["blockers"]}.values(),
            key=_blocker_key,
        )
        scan["unit_context"] = {
            **{key: value for key, value in dependencies.items() if key != "blockers"},
            "top_level": _top_level_context(unit, scan["functions"]),
        }
        scanned.append(scan)
        blockers.extend(scan["blockers"])
    globals_ = _global_records(scanned)
    global_names = {item["symbol"] for item in globals_}
    nodes = _function_records(scanned, global_names)
    blocker_catalog = build_blocker_catalog(blockers)
    validate_blocker_catalog(blocker_catalog)
    inputs = [{"unit_id": unit["unit_id"], "source": {"path": unit["path"],
        "sha256": unit["sha256"], "size_bytes": len(unit["raw"])}}
        for unit in sorted(units, key=lambda item: item["unit_id"])
    ]
    return {
        "schema_version": 2,
        "status": "ready_with_boundaries" if blockers else "ready",
        "inputs": inputs,
        "nodes": sorted(nodes, key=lambda item: item["node_id"]),
        "globals": sorted(globals_, key=lambda item: item["global_id"]),
        "unit_contexts": sorted(
            (item["unit_context"] for item in scanned),
            key=lambda item: item["unit_id"],
        ),
        "header_facts": dependency_snapshot.header_facts(),
        "parser": {
            "kind": "deterministic_lexical_c_subset",
            "limitations": list(PARSER_LIMITATIONS),
            **blocker_catalog,
            "dependency_snapshot": dependency_snapshot.report(),
        },
        "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
    }
def _validated_unit(
    root: Path, item: Mapping[str, Any], snapshot: DependencySnapshot
) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValueError("translation_units entries must be objects")
    unit_id = item.get("unit_id")
    source = item.get("source")
    if not isinstance(unit_id, str) or not unit_id:
        raise ValueError("translation unit unit_id must be a non-empty string")
    if not isinstance(source, Mapping):
        raise ValueError(f"translation unit {unit_id} source must be an object")
    path = source.get("path")
    expected = source.get("sha256")
    if not isinstance(path, str) or not _safe_relative(path):
        raise ValueError(f"translation unit {unit_id} source.path is not repo-relative POSIX")
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ValueError(f"translation unit {unit_id} source.sha256 is invalid")
    try:
        resolved = snapshot.resolve(Path(*PurePosixPath(path).parts))
    except (OSError, ValueError) as exc:
        raise ValueError(f"translation unit {unit_id} source.path escapes repo_root") from exc
    if not resolved.is_file():
        raise ValueError(f"translation unit {unit_id} source.path must be a file")
    if resolved.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError(f"translation unit {unit_id} source.path exceeds byte limit")
    with resolved.open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError(f"translation unit {unit_id} source.path exceeds byte limit")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError(f"translation unit {unit_id} source.sha256 does not match")
    return {
        "unit_id": unit_id,
        "path": path,
        "sha256": actual,
        "raw": raw,
        "compile_context": _normalize_compile_context(root, item, snapshot),
    }
def _safe_relative(value: str) -> bool:
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (bool(value) and "\\" not in value and not posix.is_absolute() and not windows.drive
            and ".." not in posix.parts and posix.as_posix() == value)
def _scan_unit(unit: dict[str, Any]) -> dict[str, Any]:
    text = unit["raw"].decode("latin-1")
    masked, lexical = _mask_non_code(text)
    blockers = [{"unit_id": unit["unit_id"], "kind": kind, "byte_offset": offset,
                 "source_path": unit["path"], "source_sha256": unit["sha256"]}
                for kind, offset in lexical]
    functions: list[dict[str, Any]] = []
    globals_: list[dict[str, Any]] = []
    start = index = 0
    while index < len(masked):
        char = masked[index]
        if char == "{":
            close = _matching(masked, index, "{", "}")
            if close is None:
                blockers.append(_source_blocker(unit, "unbalanced_brace", index))
                break
            header = masked[start:index]
            name = _function_name(header)
            if name is not None:
                source_start = start + len(header) - len(header.lstrip())
                functions.append({"symbol": name, "start": source_start, "open": index, "end": close + 1, "header": header})
                start = close + 1
            index = close + 1
            continue
        if char == ";":
            globals_.extend(_global_candidates(masked[start:index + 1], start, index + 1))
            start = index + 1
        elif char == "}":
            blockers.append(_source_blocker(unit, "unexpected_closing_brace", index))
        index += 1
    if not functions and not blockers:
        blockers.append(_source_blocker(
            unit, "translation_unit_without_function_definition", 0
        ))
    return {**unit, "masked": masked, "functions": functions,
            "globals_raw": globals_, "blockers": blockers,
            "function_spans_reliable": function_spans_reliable(functions, blockers)}
def _global_records(scanned: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for unit in scanned:
        if unit["blockers"]:
            continue
        for item in unit["globals_raw"]:
            span = unit["raw"][item["start"]:item["end"]]
            digest = hashlib.sha256(span).hexdigest()
            global_id = _content_id(
                "global", unit["unit_id"], unit["sha256"], digest, item["symbol"], item["linkage"],
            )
            records.append({"global_id": global_id, "unit_id": unit["unit_id"],
                "symbol": item["symbol"], "linkage": item["linkage"],
                "source": {"path": unit["path"], "sha256": unit["sha256"],
                "encoding": _source_content(span)[1], "span": {
                    "byte_start": item["start"], "byte_end": item["end"], "sha256": digest},
                "content": _source_content(span)[0]}})
    return records
def _function_records(scanned: Sequence[dict[str, Any]], global_names: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for unit in scanned:
        if not unit["function_spans_reliable"]:
            records.append(_boundary_node(unit))
            continue
        for item in unit["functions"]:
            span = unit["raw"][item["start"]:item["end"]]
            digest = hashlib.sha256(span).hexdigest()
            linkage = "internal" if re.search(r"\bstatic\b", item["header"]) else "external"
            node_id = _content_id(
                "function", unit["unit_id"], unit["sha256"], digest, str(item["start"]), linkage,
            )
            body = unit["masked"][item["open"] + 1:item["end"] - 1]
            locals_ = _declared_locals(item["header"], body, item["symbol"])
            calls = _direct_calls(body) - locals_
            identifiers = set(_IDENT.findall(body)) - locals_
            content, encoding = _source_content(span)
            signature_span = unit["raw"][item["start"]:item["open"]]
            signature_content, signature_encoding = _source_content(signature_span)
            records.append({"node_id": node_id, "node_kind": "function",
                "unit_id": unit["unit_id"],
                "symbol": item["symbol"], "linkage": linkage,
                "direct_calls": sorted(calls), "referenced_globals": sorted(identifiers & global_names),
                "source": {"path": unit["path"], "sha256": unit["sha256"], "encoding": encoding,
                "span": {"byte_start": item["start"], "byte_end": item["end"], "sha256": digest},
                "content": content},
                "signature": {"path": unit["path"], "sha256": unit["sha256"],
                "encoding": signature_encoding, "span": {
                    "byte_start": item["start"], "byte_end": item["open"],
                    "sha256": hashlib.sha256(signature_span).hexdigest()},
                "content": signature_content}})
    return records
def _boundary_node(unit: Mapping[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(unit["raw"]).hexdigest()
    content, encoding = _source_content(unit["raw"])
    symbol = f"c2r_unit_{digest[:16]}"
    return {
        "node_id": _content_id("translation_unit", unit["unit_id"], digest),
        "node_kind": "translation_unit_boundary",
        "unit_id": unit["unit_id"],
        "symbol": symbol,
        "linkage": "internal",
        "direct_calls": [],
        "referenced_globals": [],
        "source": {
            "path": unit["path"],
            "sha256": unit["sha256"],
            "encoding": encoding,
            "span": {"byte_start": 0, "byte_end": len(unit["raw"]), "sha256": digest},
            "content": content,
        },
    }
def _declared_locals(header: str, body: str, function_name: str) -> set[str]:
    result: set[str] = set()
    marker = re.search(rf"\b{re.escape(function_name)}\s*\(", header)
    if marker:
        opening = header.find("(", marker.start())
        closing = _matching(header, opening, "(", ")")
        if closing is not None:
            for part in _split_top_level(header[opening + 1:closing], ","):
                names = [name for name in _IDENT.findall(part) if name not in _WORDS]
                if names: result.add(names[-1])
    local_pattern = r"(?:^|[;{}])\s*(?:(?:const|volatile|signed|unsigned|short|long)\s+)*(?:char|int|float|double|_Bool|struct\s+\w+|union\s+\w+|enum\s+\w+)\s+\**\s*([A-Za-z_]\w*)"
    result.update(re.findall(local_pattern, body))
    return result
def _direct_calls(body: str) -> set[str]:
    result: set[str] = set()
    for match in _CALL.finditer(body):
        name = match.group(1)
        prefix = body[:match.start()].rstrip()
        if name not in _WORDS and not prefix.endswith(".") and not prefix.endswith("->"):
            result.add(name)
    return result
def _source_content(span: bytes) -> tuple[str, str]:
    try:
        return span.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return span.decode("latin-1"), "latin-1-byte-map"
def _source_blocker(unit: Mapping[str, Any], kind: str, offset: int) -> dict[str, Any]:
    return {"unit_id": str(unit["unit_id"]), "kind": kind,
            "byte_offset": offset, "source_path": str(unit["path"]),
            "source_sha256": str(unit["sha256"])}
def _content_id(kind: str, *parts: str) -> str:
    payload = json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return f"{kind}-{hashlib.sha256(payload).hexdigest()[:24]}"
def _blocker_key(item: Mapping[str, Any]) -> tuple[str, str, int]:
    return str(item["unit_id"]), str(item["kind"]), int(item.get("byte_offset", -1))
build_c_index = index_translation_units
__all__ = ["PARSER_LIMITATIONS", "build_c_index", "index_translation_units"]
