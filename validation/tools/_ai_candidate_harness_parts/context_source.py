from __future__ import annotations

from pathlib import Path
from typing import Any

from .context_security import (
    is_absolute_any_platform,
    logical_path,
    redact_text,
    resolve_under,
    sha256_bytes,
    sha256_path,
)


MAX_SOURCE_SPAN_BYTES = 32_000


def build_source_context(
    spec: dict[str, Any],
    *,
    source_root: Path | None,
    known_roots: tuple[str, ...],
) -> tuple[dict[str, Any], str | None]:
    descriptor = source_descriptor(spec)
    source_file = descriptor.get("file")
    commit = source_commit(spec)
    base = {
        "source_commit": redact_text(commit, known_roots) if commit else None,
        "source_file": normalize_declared_path(source_file),
    }
    if source_root is None or not isinstance(source_file, str) or not source_file:
        return inline_source_context(spec, base, known_roots), source_file if isinstance(source_file, str) else None

    try:
        source_path = resolve_under(source_root, source_file)
    except ValueError:
        return {**base, "span": {"status": "blocked_path_outside_source_root"}}, source_file
    if not source_path.is_file():
        return {**base, "span": {"status": "source_file_missing"}}, source_file

    full_sha256 = sha256_path(source_path)
    expected_full_sha256 = expected_source_sha256(spec, source_file)
    binding = {
        "path": logical_path(source_root, source_path),
        "sha256": full_sha256,
        "size_bytes": source_path.stat().st_size,
    }
    if expected_full_sha256 and expected_full_sha256 != full_sha256:
        return {
            **base,
            "input": binding,
            "span": {
                "status": "blocked_source_hash_mismatch",
                "expected_source_sha256": expected_full_sha256,
                "actual_source_sha256": full_sha256,
            },
        }, source_file

    try:
        content_bytes, coordinates = extract_span(source_path, descriptor, spec.get("c_source"))
    except ValueError as error:
        return {**base, "input": binding, "span": {"status": str(error)}}, source_file
    content_sha256 = sha256_bytes(content_bytes)
    expected_span_sha256 = descriptor.get("sha256")
    if isinstance(expected_span_sha256, str) and expected_span_sha256 and expected_span_sha256 != content_sha256:
        return {
            **base,
            "input": binding,
            "span": {
                "status": "blocked_span_hash_mismatch",
                "expected_sha256": expected_span_sha256,
                "actual_sha256": content_sha256,
                **coordinates,
            },
        }, source_file
    if len(content_bytes) > MAX_SOURCE_SPAN_BYTES:
        return {
            **base,
            "input": binding,
            "span": {
                "status": "omitted_too_large",
                "sha256": content_sha256,
                "size_bytes": len(content_bytes),
                **coordinates,
            },
        }, source_file
    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {
            **base,
            "input": binding,
            "span": {"status": "unsupported_source_encoding", "sha256": content_sha256, **coordinates},
        }, source_file
    return {
        **base,
        "input": binding,
        "span": {
            "status": "real_source_bound",
            "sha256": content_sha256,
            "size_bytes": len(content_bytes),
            "content": redact_text(content, known_roots),
            **coordinates,
        },
    }, source_file


def source_descriptor(spec: dict[str, Any]) -> dict[str, Any]:
    top_level = spec.get("function_source_span")
    if isinstance(top_level, dict):
        descriptor = dict(top_level)
        if not isinstance(descriptor.get("file"), str):
            source_file = spec.get("source_file")
            source = spec.get("source")
            if not isinstance(source_file, str) and isinstance(source, dict):
                source_file = source.get("source_file")
            if isinstance(source_file, str):
                descriptor["file"] = source_file
        return descriptor
    boundary = spec.get("c_boundary")
    signatures = boundary.get("signatures") if isinstance(boundary, dict) else None
    function_name = spec.get("function_name")
    if isinstance(signatures, list):
        for signature in signatures:
            if not isinstance(signature, dict) or signature.get("function") != function_name:
                continue
            span = signature.get("source_span")
            if isinstance(span, dict):
                return dict(span)
        for signature in signatures:
            if isinstance(signature, dict) and isinstance(signature.get("source_span"), dict):
                return dict(signature["source_span"])
    source_file = spec.get("source_file")
    source = spec.get("source")
    if not isinstance(source_file, str) and isinstance(source, dict):
        source_file = source.get("source_file")
    if not isinstance(source_file, str) and isinstance(boundary, dict):
        files = boundary.get("files")
        if isinstance(files, list):
            source_entry = next(
                (item for item in files if isinstance(item, dict) and item.get("role") == "source"),
                None,
            )
            source_file = source_entry.get("path") if isinstance(source_entry, dict) else None
    return {"file": source_file} if isinstance(source_file, str) else {}


def extract_span(path: Path, descriptor: dict[str, Any], inline_source: Any) -> tuple[bytes, dict[str, int]]:
    byte_start = descriptor.get("byte_start")
    byte_end = descriptor.get("byte_end")
    if isinstance(byte_start, int) and isinstance(byte_end, int) and 0 <= byte_start < byte_end:
        requested = byte_end - byte_start
        if requested > MAX_SOURCE_SPAN_BYTES:
            raise ValueError("source_span_too_large")
        with path.open("rb") as stream:
            stream.seek(byte_start)
            content = stream.read(requested)
        expected = descriptor.get("sha256")
        if isinstance(expected, str) and sha256_bytes(content) != expected:
            with path.open("rb") as stream:
                stream.seek(byte_start)
                inclusive = stream.read(requested + 1)
            if sha256_bytes(inclusive) == expected:
                return inclusive, {"byte_start": byte_start, "byte_end": byte_end, "byte_end_inclusive": 1}
        return content, {"byte_start": byte_start, "byte_end": byte_end}

    line_start = descriptor.get("line_start")
    line_end = descriptor.get("line_end")
    if isinstance(line_start, int) and isinstance(line_end, int) and 1 <= line_start <= line_end:
        selected: list[bytes] = []
        total = 0
        with path.open("rb") as stream:
            for number, line in enumerate(stream, start=1):
                if number < line_start:
                    continue
                if number > line_end:
                    break
                total += len(line)
                if total > MAX_SOURCE_SPAN_BYTES:
                    raise ValueError("source_span_too_large")
                selected.append(line)
        if not selected:
            raise ValueError("source_span_empty")
        return b"".join(selected), {"line_start": line_start, "line_end": line_end}

    if isinstance(inline_source, str) and inline_source:
        needle = inline_source.encode("utf-8")
        if len(needle) > MAX_SOURCE_SPAN_BYTES:
            raise ValueError("source_span_too_large")
        data = path.read_bytes()
        first = data.find(needle)
        if first >= 0 and data.find(needle, first + 1) < 0:
            return needle, {"byte_start": first, "byte_end": first + len(needle)}
    raise ValueError("source_span_coordinates_missing")


def inline_source_context(
    spec: dict[str, Any],
    base: dict[str, Any],
    known_roots: tuple[str, ...],
) -> dict[str, Any]:
    inline = spec.get("c_source")
    if not isinstance(inline, str) or not inline:
        return {**base, "span": {"status": "source_span_unavailable"}}
    data = inline.encode("utf-8")
    if len(data) > MAX_SOURCE_SPAN_BYTES:
        return {
            **base,
            "span": {"status": "omitted_too_large", "sha256": sha256_bytes(data), "size_bytes": len(data)},
        }
    return {
        **base,
        "span": {
            "status": "inline_slice_spec",
            "sha256": sha256_bytes(data),
            "size_bytes": len(data),
            "content": redact_text(inline, known_roots),
        },
    }


def expected_source_sha256(spec: dict[str, Any], source_file: str) -> str | None:
    candidates = [spec.get("source_file_hashes")]
    source = spec.get("source")
    if isinstance(source, dict):
        candidates.append(source.get("source_file_hashes"))
    normalized = Path(source_file).as_posix().lstrip("./")
    for mapping in candidates:
        if not isinstance(mapping, dict):
            continue
        for key, value in mapping.items():
            if Path(str(key)).as_posix().lstrip("./") == normalized and isinstance(value, str):
                return value
    return None


def source_commit(spec: dict[str, Any]) -> str | None:
    value = spec.get("source_commit")
    source = spec.get("source")
    if not isinstance(value, str) and isinstance(source, dict):
        value = source.get("source_commit")
    return value if isinstance(value, str) else None


def normalize_declared_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if is_absolute_any_platform(value) or ".." in path.parts:
        return "<invalid-source-path>"
    return path.as_posix()
