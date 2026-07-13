from __future__ import annotations

import re
from typing import Any

from .artifacts import content_sha256
from .rust_candidate_facts import IDENTIFIER, mask_rust_non_code


SHA256 = re.compile(r"^[0-9a-f]{64}$")


class NoFfiBoundaryError(ValueError):
    pass


def derive_boundary_manifest(source: str, candidate_sha256: str) -> dict[str, Any]:
    if SHA256.fullmatch(candidate_sha256) is None:
        raise ValueError("boundary manifest candidate SHA-256 is invalid")
    masked = mask_rust_non_code(source, preserve_string_delimiters=True)
    direct = set(re.findall(
        rf"\bextern\s*(?:\"[^\"]*\"\s*)?(?:unsafe\s+)?fn\s+({IDENTIFIER})",
        masked,
    ))
    imports = _foreign_links(source, masked)
    exports = _export_links(source, masked)
    all_symbols = direct | set(imports) | set(exports)
    if not all_symbols:
        raise NoFfiBoundaryError(
            "preserved FFI candidate has no host-detectable C ABI boundary"
        )
    manifest = {
        "schema_version": 1,
        "mode": "preserve_ffi_boundary",
        "candidate_sha256": candidate_sha256,
        "extern_c_symbols": sorted(all_symbols),
        "imported_symbols": sorted(imports),
        "exported_symbols": sorted(exports),
        "imported_links": [imports[symbol] for symbol in sorted(imports)],
        "exported_links": [exports[symbol] for symbol in sorted(exports)],
        "semantic_acceptance": False,
    }
    manifest["manifest_sha256"] = content_sha256(manifest)
    return manifest


def derive_ffi_boundary_facts(
    source: str, candidate_sha256: str,
) -> list[dict[str, str]]:
    manifest = derive_boundary_manifest(source, candidate_sha256)
    imports = {
        (item["rust_symbol"], item["link_name"], item["abi"])
        for item in manifest["imported_links"]
    }
    exports = {
        (item["rust_symbol"], item["link_name"], item["abi"])
        for item in manifest["exported_links"]
    }
    return [{
        "symbol": symbol, "link_name": link_name, "abi": abi,
        "direction": (
            "import-export" if key in imports and key in exports
            else ("import" if key in imports else "export")
        ),
    } for key in sorted(imports | exports) for symbol, link_name, abi in (key,)]


def _foreign_links(source: str, masked: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    blocks = re.compile(
        r"\b(?:unsafe\s+)?extern\s*(?:\"[^\"]*\"\s*)?\{(?P<body>[^{}]*)\}",
        re.DOTALL,
    )
    declarations = re.compile(
        rf"(?P<attrs>(?:#\s*\[[^\]]*\]\s*)*)"
        rf"\b(?:safe\s+|unsafe\s+)?(?:fn|static(?:\s+mut)?)\s+"
        rf"(?P<symbol>{IDENTIFIER})"
    )
    for block in blocks.finditer(masked):
        abi = _extern_abi(source[block.start():block.start("body")])
        body_start = block.start("body")
        for declaration in declarations.finditer(block.group("body")):
            symbol = declaration.group("symbol")
            attrs_start = body_start + declaration.start("attrs")
            attrs_end = body_start + declaration.end("attrs")
            explicit = _attribute_name(source[attrs_start:attrs_end], "link_name")
            result[symbol] = {
                "rust_symbol": symbol,
                "link_name": explicit if explicit is not None else symbol,
                "abi": abi,
            }
    return result


def _export_links(source: str, masked: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    declarations = re.compile(
        rf"(?P<attrs>(?:#\s*\[[^\]]*\]\s*)+)"
        rf"(?:pub(?:\s*\([^)]*\))?\s+)?(?:unsafe\s+)?"
        rf"(?:extern\s*(?:\"[^\"]*\"\s*)?)?"
        rf"(?:fn|static(?:\s+mut)?)\s+(?P<symbol>{IDENTIFIER})"
    )
    for declaration in declarations.finditer(masked):
        attrs_masked = declaration.group("attrs")
        if re.search(r"\b(?:no_mangle|export_name)\b", attrs_masked) is None:
            continue
        symbol = declaration.group("symbol")
        attrs = source[declaration.start("attrs"):declaration.end("attrs")]
        explicit = _attribute_name(attrs, "export_name")
        result[symbol] = {
            "rust_symbol": symbol,
            "link_name": explicit if explicit is not None else symbol,
            "abi": _extern_abi(source[declaration.start():declaration.end()]),
        }
    public_extern = re.compile(
        rf"\bpub(?:\s*\([^)]*\))?\s+(?:unsafe\s+)?extern\s*"
        rf"(?:\"[^\"]*\"\s*)?fn\s+(?P<symbol>{IDENTIFIER})"
    )
    for declaration in public_extern.finditer(masked):
        symbol = declaration.group("symbol")
        result.setdefault(symbol, {
            "rust_symbol": symbol, "link_name": symbol,
            "abi": _extern_abi(source[declaration.start():declaration.end()]),
        })
    return result


def _attribute_name(attributes: str, name: str) -> str | None:
    match = re.search(
        rf"\b{re.escape(name)}\s*=\s*(?:"
        rf"r(?P<hashes>#{{0,255}})\"(?P<raw>.*?)\"(?P=hashes)|"
        rf"\"(?P<cooked>(?:\\.|[^\"\\])*)\")",
        attributes,
        re.DOTALL,
    )
    if match is None:
        return None
    raw = match.group("raw")
    return raw if raw is not None else _decode_cooked(match.group("cooked"))


def _decode_cooked(value: str) -> str:
    output: list[str] = []
    index = 0
    simple = {"n": "\n", "r": "\r", "t": "\t", "0": "\0", "\\": "\\", '"': '"'}
    while index < len(value):
        if value[index] != "\\":
            output.append(value[index])
            index += 1
            continue
        index += 1
        if index >= len(value):
            raise ValueError("Rust FFI link name has an incomplete escape")
        escape = value[index]
        if escape in simple:
            output.append(simple[escape])
            index += 1
        elif escape == "x":
            digits = value[index + 1:index + 3]
            if len(digits) != 2 or re.fullmatch(r"[0-9A-Fa-f]{2}", digits) is None:
                raise ValueError("Rust FFI link name has an invalid hex escape")
            output.append(chr(int(digits, 16)))
            index += 3
        elif escape == "u":
            found = re.match(r"\{([0-9A-Fa-f_]{1,8})\}", value[index + 1:])
            if found is None:
                raise ValueError("Rust FFI link name has an invalid Unicode escape")
            codepoint = int(found.group(1).replace("_", ""), 16)
            if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
                raise ValueError("Rust FFI link name has an invalid Unicode scalar")
            output.append(chr(codepoint))
            index += found.end() + 1
        elif escape in {"\n", "\r"}:
            if escape == "\r" and value[index + 1:index + 2] == "\n":
                index += 1
            index += 1
            while index < len(value) and value[index].isspace():
                index += 1
        else:
            raise ValueError("Rust FFI link name has an unsupported escape")
    return "".join(output)


def _extern_abi(fragment: str) -> str:
    match = re.search(r"\bextern\s*(?:\"([^\"]*)\")?", fragment)
    return (match.group(1) or "C") if match is not None else "C"


__all__ = [
    "NoFfiBoundaryError", "derive_boundary_manifest", "derive_ffi_boundary_facts",
]
