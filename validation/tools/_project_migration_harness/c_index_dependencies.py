from __future__ import annotations

import hashlib
import re
from collections import deque
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .build_facts import file_binding, repository_path, resolve_repository_path
from .ledger_security import assert_no_secrets


MAX_HEADER_BYTES = 2 * 1024 * 1024
MAX_HEADER_TOTAL_BYTES = 32 * 1024 * 1024
MAX_HEADERS = 512
MAX_INCLUDE_DEPTH = 32
_INCLUDE = re.compile(r'^\s*([<"])([^>"]+)[>"]\s*$')
_DIRECTIVE = re.compile(r'^\s*#\s*([A-Za-z_]\w*)\b(.*)$', re.DOTALL)


def normalize_compile_context(
    repo_root: Path, item: Mapping[str, Any]
) -> dict[str, Any]:
    working = _repo_value(repo_root, item.get("working_directory", "."), "working_directory")
    includes: list[dict[str, str]] = []
    raw_includes = item.get("includes", [])
    if not _sequence(raw_includes) or not all(isinstance(value, Mapping) for value in raw_includes):
        raise ValueError("translation unit includes must be an array of objects")
    for value in raw_includes:
        kind, scope, path = value.get("kind"), value.get("scope"), value.get("path")
        if kind not in {"user", "system", "quote", "after", "forced", "macros"}:
            raise ValueError("translation unit include kind is invalid")
        if scope == "external" and path == "<external-path>":
            includes.append({"kind": str(kind), "scope": "external", "path": str(path)})
        elif scope == "repository":
            includes.append({
                "kind": str(kind), "scope": "repository",
                "path": _repo_value(repo_root, path, "include path"),
            })
        else:
            raise ValueError("translation unit include binding is invalid")
    defines: list[dict[str, str]] = []
    raw_defines = item.get("defines", [])
    if not _sequence(raw_defines) or not all(isinstance(value, Mapping) for value in raw_defines):
        raise ValueError("translation unit defines must be an array of objects")
    for value in raw_defines:
        name, assigned = value.get("name"), value.get("value")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError("translation unit define name is invalid")
        if not isinstance(assigned, str) or len(assigned.encode("utf-8")) > 512:
            raise ValueError("translation unit define value is invalid")
        defines.append({"name": name, "value": assigned})
    flags = item.get("semantic_flags", [])
    if not _sequence(flags) or not all(isinstance(value, str) for value in flags):
        raise ValueError("translation unit semantic_flags must be an array of strings")
    redacted = item.get("redacted_define_count", 0)
    if isinstance(redacted, bool) or not isinstance(redacted, int) or redacted < 0:
        raise ValueError("translation unit redacted_define_count is invalid")
    context = {
        "compiler": str(item.get("compiler", "unknown")),
        "language": str(item.get("language", "c")),
        "working_directory": working,
        "includes": sorted(includes, key=lambda value: (value["kind"], value["path"])),
        "defines": sorted(defines, key=lambda value: value["name"]),
        "redacted_define_count": redacted,
        "semantic_flags": list(flags),
    }
    assert_no_secrets(context, "compile_context")
    return context


def dependency_context(repo_root: Path, unit: Mapping[str, Any]) -> dict[str, Any]:
    compile_context = dict(unit["compile_context"])
    source_path = repo_root.joinpath(*PurePosixPath(str(unit["path"])).parts)
    search_dirs = _search_directories(repo_root, source_path, compile_context["includes"])
    include_records: list[dict[str, Any]] = []
    headers: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    queued: deque[tuple[Path, int]] = deque()
    for include in compile_context["includes"]:
        if include["kind"] not in {"forced", "macros"}:
            continue
        if include["scope"] != "repository":
            blockers.append(_blocker(unit, "external_forced_include", 0))
            continue
        target = repo_root.joinpath(*PurePosixPath(include["path"]).parts)
        queued.append((target, 0))
    _queue_directives(
        repo_root, source_path, bytes(unit["raw"]), search_dirs, include_records,
        blockers, queued, unit, 0,
    )
    visited: set[str] = set()
    total = 0
    while queued:
        path, depth = queued.popleft()
        if depth > MAX_INCLUDE_DEPTH:
            blockers.append(_blocker(unit, "include_depth_limit_exceeded", 0))
            continue
        try:
            binding = file_binding(repo_root, path, max_bytes=MAX_HEADER_BYTES)
        except (OSError, ValueError):
            blockers.append(_blocker(unit, "include_binding_invalid", 0))
            continue
        if binding["path"] in visited:
            continue
        if len(visited) >= MAX_HEADERS:
            blockers.append(_blocker(unit, "include_file_limit_exceeded", 0))
            break
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
            blockers.append(_blocker(unit, "include_binding_changed", 0))
            continue
        total += len(raw)
        if total > MAX_HEADER_TOTAL_BYTES:
            blockers.append(_blocker(unit, "include_total_size_limit_exceeded", 0))
            break
        visited.add(binding["path"])
        content, encoding = _source_content(raw)
        headers.append({"source": {
            **binding,
            "encoding": encoding,
            "span": {
                "byte_start": 0,
                "byte_end": len(raw),
                "sha256": binding["sha256"],
            },
            "content": content,
        }})
        _queue_directives(
            repo_root, path, raw, search_dirs, include_records, blockers, queued,
            unit, depth + 1,
        )
    if compile_context["redacted_define_count"]:
        blockers.append(_blocker(unit, "redacted_compile_define", 0))
    return {
        "unit_id": unit["unit_id"],
        "compile_context": compile_context,
        "includes": sorted(include_records, key=lambda value: (
            value["from_path"], value["byte_offset"], value["target"]
        )),
        "headers": sorted(headers, key=lambda value: value["source"]["path"]),
        "blockers": sorted(
            {tuple(sorted(item.items())): item for item in blockers}.values(),
            key=lambda value: (value["kind"], value["byte_offset"]),
        ),
    }


def top_level_context(unit: Mapping[str, Any], functions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raw = bytes(unit["raw"])
    masked = bytearray(raw)
    spans = []
    for function in sorted(functions, key=lambda value: int(value["start"])):
        start, end = int(function["start"]), int(function["end"])
        if start < 0 or end < start or end > len(raw):
            raise ValueError("function span is outside the translation unit")
        spans.append({"byte_start": start, "byte_end": end})
        for index in range(start, end):
            if masked[index] not in {10, 13}:
                masked[index] = 32
    content, encoding = _source_content(bytes(masked))
    return {
        "source": {
            "path": unit["path"], "sha256": unit["sha256"], "encoding": encoding,
            "span": {"byte_start": 0, "byte_end": len(raw),
                     "sha256": hashlib.sha256(bytes(masked)).hexdigest()},
            "content": content,
        },
        "coverage": {
            "source_size_bytes": len(raw), "function_spans": spans,
            "top_level_projection_sha256": hashlib.sha256(bytes(masked)).hexdigest(),
            "uncovered_ranges": [], "status": "complete",
        },
    }


def _queue_directives(
    repo_root: Path, source: Path, raw: bytes, search_dirs: Sequence[Path],
    records: list[dict[str, Any]], blockers: list[dict[str, Any]],
    queue: deque[tuple[Path, int]], unit: Mapping[str, Any], depth: int,
) -> None:
    for directive in _directives(raw):
        if directive["kind"] in {"if", "ifdef", "ifndef", "elif", "else", "endif"} and depth:
            blockers.append(_blocker(unit, "header_conditional_preprocessor", directive["byte_offset"]))
        if directive["kind"] != "include":
            continue
        parsed = _INCLUDE.fullmatch(directive["body"])
        if parsed is None:
            records.append({**directive, "from_path": repository_path(repo_root, source),
                            "target": "<dynamic>", "status": "unresolved"})
            blockers.append(_blocker(unit, "dynamic_include_unresolved", directive["byte_offset"]))
            continue
        style, target = parsed.groups()
        resolved = _resolve_include(repo_root, source, target, style == '"', search_dirs)
        record = {**directive, "from_path": repository_path(repo_root, source),
                  "target": target, "style": "quote" if style == '"' else "system"}
        if resolved is None:
            records.append({**record, "status": "external_or_unresolved"})
            blockers.append(_blocker(unit, "include_dependency_unresolved", directive["byte_offset"]))
        else:
            records.append({**record, "status": "bound", "path": repository_path(repo_root, resolved)})
            queue.append((resolved, depth))


def _directives(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("latin-1")
    result = []
    offset = 0
    while offset < len(text):
        end = text.find("\n", offset)
        end = len(text) if end < 0 else end + 1
        while end < len(text) and text[offset:end].rstrip("\r\n").endswith("\\"):
            following = text.find("\n", end)
            end = len(text) if following < 0 else following + 1
        logical = text[offset:end]
        match = _DIRECTIVE.match(logical)
        if match:
            result.append({"kind": match.group(1).lower(), "body": match.group(2).strip(),
                           "byte_offset": offset,
                           "sha256": hashlib.sha256(raw[offset:end]).hexdigest()})
        offset = end
    return result


def _resolve_include(
    repo_root: Path, source: Path, target: str, quote: bool, search_dirs: Sequence[Path]
) -> Path | None:
    candidate = PurePosixPath(target)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in target:
        return None
    roots = ([source.parent] if quote else []) + list(search_dirs)
    for base in roots:
        try:
            resolved = resolve_repository_path(repo_root, Path(*candidate.parts), base=base)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _search_directories(
    repo_root: Path, source: Path, includes: Sequence[Mapping[str, str]]
) -> list[Path]:
    result = [source.parent]
    for include in includes:
        if include["scope"] != "repository" or include["kind"] in {"forced", "macros"}:
            continue
        path = repo_root.joinpath(*PurePosixPath(include["path"]).parts)
        if path.is_dir() and path not in result:
            result.append(path)
    return result


def _repo_value(repo_root: Path, value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"translation unit {label} is invalid")
    try:
        return repository_path(repo_root, resolve_repository_path(repo_root, Path(*PurePosixPath(value).parts)))
    except (OSError, ValueError) as error:
        raise ValueError(f"translation unit {label} is outside the repository") from error


def _blocker(unit: Mapping[str, Any], kind: str, offset: int) -> dict[str, Any]:
    return {"unit_id": str(unit["unit_id"]), "kind": kind, "byte_offset": int(offset)}


def _source_content(raw: bytes) -> tuple[str, str]:
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1-byte-map"


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


__all__ = ["dependency_context", "normalize_compile_context", "top_level_context"]
