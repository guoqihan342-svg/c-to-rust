from __future__ import annotations

import re
from typing import Any

from .artifacts import content_sha256


SHA256 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"


def derive_rust_metadata(source: str) -> dict[str, Any]:
    masked = mask_rust_non_code(source)
    unsafe_count = len(re.findall(r"\bunsafe\b", masked))
    public_pattern = re.compile(
        rf"\bpub(?:\s*\([^)]*\))?\s+"
        rf"(?:(?:async|const|unsafe)\s+)*(?:extern\s+)?"
        rf"(?:fn|struct|enum|union|trait|type|const|static|mod)\s+({IDENTIFIER})"
    )
    public = set(public_pattern.findall(masked))
    required: set[str] = set()
    for statement in re.findall(r"\buse\s+([^;]+);", masked, re.DOTALL):
        aliases = re.findall(rf"\bas\s+({IDENTIFIER})", statement)
        if aliases:
            required.update(aliases)
            continue
        identifiers = re.findall(IDENTIFIER, statement)
        required.update(
            item for item in identifiers[-1:]
            if item not in {"crate", "self", "super"}
        )
    required.update(re.findall(rf"\b(?:crate|super)\s*::\s*({IDENTIFIER})", masked))
    return {
        "public_symbols": sorted(public),
        "required_symbols": sorted(required - public),
        "unsafe_count": unsafe_count,
    }


def derive_boundary_manifest(source: str, candidate_sha256: str) -> dict[str, Any]:
    if SHA256.fullmatch(candidate_sha256) is None:
        raise ValueError("boundary manifest candidate SHA-256 is invalid")
    masked = mask_rust_non_code(source, preserve_string_delimiters=True)
    direct = set(re.findall(
        rf"\bextern\s*(?:\"[^\"]*\"\s*)?(?:unsafe\s+)?fn\s+({IDENTIFIER})",
        masked,
    ))
    declared = set(direct)
    for body in re.findall(
        r"\b(?:unsafe\s+)?extern\s*(?:\"[^\"]*\"\s*)?\{([^{}]*)\}",
        masked,
        re.DOTALL,
    ):
        declared.update(re.findall(rf"\b(?:safe\s+|unsafe\s+)?fn\s+({IDENTIFIER})", body))
        declared.update(re.findall(rf"\bstatic(?:\s+mut)?\s+({IDENTIFIER})", body))
    exports = set(re.findall(
        rf"#\s*\[\s*(?:unsafe\s*\(\s*)?(?:no_mangle|export_name)[^\]]*\]"
        rf"[\s\S]{{0,256}}?\b(?:fn|static)\s+({IDENTIFIER})",
        masked,
    ))
    exports.update(re.findall(
        rf"\bpub\s+(?:unsafe\s+)?extern\s*(?:\"[^\"]*\"\s*)?fn\s+({IDENTIFIER})",
        masked,
    ))
    if not declared and not exports:
        raise ValueError("preserved FFI candidate has no host-detectable C ABI boundary")
    manifest = {
        "schema_version": 1,
        "mode": "preserve_ffi_boundary",
        "candidate_sha256": candidate_sha256,
        "extern_c_symbols": sorted(declared),
        "exported_symbols": sorted(exports),
        "semantic_acceptance": False,
    }
    manifest["manifest_sha256"] = content_sha256(manifest)
    return manifest


def mask_rust_non_code(
    source: str, *, preserve_string_delimiters: bool = False,
) -> str:
    output = list(source)
    index = 0
    while index < len(source):
        pair = source[index:index + 2]
        if pair == "//":
            end = source.find("\n", index)
            end = len(source) if end < 0 else end
            _blank(output, source, index, end)
            index = end
            continue
        if pair == "/*":
            end = _block_comment_end(source, index)
            _blank(output, source, index, end)
            index = end
            continue
        raw = _raw_string_end(source, index)
        if raw is not None:
            start, end = raw
            _blank(output, source, start, end, delimiters=preserve_string_delimiters)
            index = end
            continue
        if source[index] == '"':
            end = _quoted_end(source, index, '"')
            _blank(output, source, index, end, delimiters=preserve_string_delimiters)
            index = end
            continue
        if source[index] == "'":
            end = _char_literal_end(source, index)
            if end is not None:
                _blank(output, source, index, end)
                index = end
                continue
        index += 1
    return "".join(output)


def _block_comment_end(source: str, start: int) -> int:
    depth, index = 1, start + 2
    while index < len(source) and depth:
        if source[index:index + 2] == "/*":
            depth += 1
            index += 2
        elif source[index:index + 2] == "*/":
            depth -= 1
            index += 2
        else:
            index += 1
    return index


def _raw_string_end(source: str, index: int) -> tuple[int, int] | None:
    match = re.match(r"(?:br|cr|r)(#{0,255})\"", source[index:])
    if match is None:
        return None
    hashes = match.group(1)
    closing = '"' + hashes
    content_start = index + match.end()
    found = source.find(closing, content_start)
    return index, len(source) if found < 0 else found + len(closing)


def _quoted_end(source: str, start: int, quote: str) -> int:
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
        elif source[index] == quote:
            return index + 1
        elif source[index] == "\n":
            return index
        else:
            index += 1
    return len(source)


def _char_literal_end(source: str, start: int) -> int | None:
    end = _quoted_end(source, start, "'")
    if end <= start + 2 or end > len(source) or source[end - 1] != "'":
        return None
    return end


def _blank(
    output: list[str], source: str, start: int, end: int, *, delimiters: bool = False,
) -> None:
    for position in range(start, min(end, len(source))):
        if delimiters and source[position] in {'"', '#'}:
            continue
        output[position] = "\n" if source[position] == "\n" else " "


__all__ = ["derive_boundary_manifest", "derive_rust_metadata", "mask_rust_non_code"]
