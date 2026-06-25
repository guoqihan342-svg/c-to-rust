"""Generate a slice spec by extracting one function from real C source."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, NamedTuple


class FunctionSlice(NamedTuple):
    function_name: str
    signature: str
    c_source: str
    line_start: int
    line_end: int
    byte_start: int
    byte_end: int


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--source-file", required=True, type=Path)
    parser.add_argument("--function", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--slice-id", required=True)
    parser.add_argument("--source-commit")
    parser.add_argument("--compiler-command-source", default="unknown")
    parser.add_argument("--include-path", dest="include_paths", action="append", default=[])
    parser.add_argument("--define", dest="defines", action="append", default=[])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    spec = generate_slice_spec(
        repo_root=args.repo_root,
        source_file=args.source_file,
        function_name=args.function,
        target_id=args.target_id,
        slice_id=args.slice_id,
        source_commit=args.source_commit,
        compiler_command_source=args.compiler_command_source,
        include_paths=args.include_paths,
        defines=args.defines,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "generated", "path": str(args.out), "slice_id": args.slice_id}, ensure_ascii=False))
    return 0


def generate_slice_spec(
    *,
    repo_root: Path,
    source_file: Path,
    function_name: str,
    target_id: str,
    slice_id: str,
    source_commit: str | None = None,
    compiler_command_source: str = "unknown",
    include_paths: list[str] | None = None,
    defines: list[str] | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    relative_source = normalize_relative_path(source_file)
    source_path = (root / relative_source).resolve()
    ensure_inside_root(root, source_path)
    text = source_path.read_text(encoding="utf-8")
    extracted = extract_function(text, function_name)
    commit = source_commit or git_commit(root)
    file_hash = sha256(source_path)

    signature = parse_signature(extracted.signature, function_name)
    return_type = signature["return_type"]
    parameters = signature["parameters"]

    return {
        "schema_version": 1,
        "target_id": target_id,
        "slice_id": slice_id,
        "level": "L3",
        "status": "draft",
        "function_name": function_name,
        "c_source": extracted.c_source,
        "source_commit": commit,
        "fixture_hash": f"{slice_id}-fixture",
        "l1_evidence": {
            "path": f"validation/evidence/{target_id}/l1-native-build.json",
            "status": "required",
            "accepted": False,
        },
        "source": {
            "source_root": str(root),
            "source_commit": commit,
            "repo_commit": commit,
            "source_file_hashes": {relative_source: file_hash},
        },
        "c_boundary": {
            "files": [
                {
                    "path": relative_source,
                    "role": "source",
                    "sha256": file_hash,
                }
            ],
            "functions": [function_name],
            "signatures": [
                {
                    "function": function_name,
                    "return_type": return_type,
                    "parameters": parameters,
                    "c_source": extracted.c_source,
                    "source_span": {
                        "file": relative_source,
                        "line_start": extracted.line_start,
                        "line_end": extracted.line_end,
                        "byte_start": extracted.byte_start,
                        "byte_end": extracted.byte_end,
                        "sha256": sha256_text(extracted.c_source),
                    },
                    "definition_status": "real_source_bound",
                }
            ],
            "direct_dependencies": direct_type_dependencies(return_type, parameters),
            "extraction": {
                "extractor": "validation/tools/extract_source_slice.py",
                "frontend": "bounded-c-source-scanner",
                "semantic_status": "syntax-indexed; compile-profile evidence required before accepted translation",
            },
        },
        "build_profile": {
            "profile_id": f"{target_id}-{slice_id}-real-source",
            "compiler_command_source": compiler_command_source,
            "include_paths": include_paths or [],
            "defines": defines or [],
            "target": {
                "triple_or_abi": "unknown",
                "endianness": "unknown",
                "int_width": 32,
                "long_width": 64,
                "pointer_width": 64,
            },
            "preprocessing_mode": "manual_flags",
            "tool_versions": {
                "extract_source_slice": "0.1.0",
            },
            "clang_type_extraction": {
                "available": False,
                "diagnostics": [
                    "syntax-indexed real source slice; clang/libclang or compile_commands semantic evidence required for accepted translation"
                ],
            },
        },
        "fixture_contract": {
            "fixture_id": f"{slice_id}-fixture",
            "path": f"validation/l2_slices/fixtures/{slice_id}.json",
            "hash": f"{slice_id}-fixture",
            "cases": [],
            "observable_outputs": ["return_code"],
            "behavior_fields": ["return_code"],
        },
        "rust_boundary": {
            "crate": "validation/l2_slices",
            "module": f"validation/l2_slices/src/{rust_module_name(function_name)}.rs",
            "public_api": [
                {
                    "name": function_name,
                    "visibility": "public",
                    "boundary_kind": "internal_ffi",
                }
            ],
            "raw_pointer_policy": "internal_only",
            "unsafe_policy": {
                "max_first_party_non_test_ratio": 0.1,
                "ledger_required": True,
            },
        },
        "claim_boundary": {
            "accepted_metadata_differences": [],
            "non_goals": [
                "No full project migration claim.",
                "No semantic equivalence claim before L3 oracle/replay/diff evidence passes.",
                "No claim that syntax-only extraction proves typedef, macro, ABI, or layout semantics.",
            ],
            "must_not_claim": [
                "full automatic C99/C11 translation",
                "whole-project migration",
                "semantic equivalence without C oracle and Rust replay evidence",
            ],
        },
        "accepted_metadata_differences": [],
        "non_goals": [
            "No full project migration claim.",
            "No semantic equivalence claim before L3 oracle/replay/diff evidence passes.",
            "No claim that syntax-only extraction proves typedef, macro, ABI, or layout semantics.",
        ],
        "cache_invalidation_keys": [
            "source.source_commit",
            "source.source_file_hashes",
            "c_boundary.signatures[0].source_span.sha256",
            "build_profile.profile_id",
            "translator_version",
        ],
    }


def extract_function(text: str, function_name: str) -> FunctionSlice:
    masked = mask_comments_and_strings(text)
    pattern = re.compile(rf"\b{re.escape(function_name)}\s*\(")
    for match in pattern.finditer(masked):
        open_paren = masked.find("(", match.start())
        close_paren = find_matching(masked, open_paren, "(", ")")
        if close_paren is None:
            continue
        body_start = skip_whitespace(masked, close_paren + 1)
        if body_start >= len(masked) or masked[body_start] != "{":
            continue
        signature_start = find_signature_start(masked, match.start())
        if signature_start is None:
            continue
        body_end = find_matching(masked, body_start, "{", "}")
        if body_end is None:
            continue
        byte_start = signature_start
        byte_end = body_end + 1
        c_source = text[byte_start:byte_end].strip()
        line_start = text.count("\n", 0, byte_start) + 1
        line_end = text.count("\n", 0, byte_end) + 1
        signature = text[byte_start:body_start].strip()
        return FunctionSlice(
            function_name=function_name,
            signature=signature,
            c_source=c_source,
            line_start=line_start,
            line_end=line_end,
            byte_start=byte_start,
            byte_end=byte_end,
        )
    raise SystemExit(f"function {function_name!r} not found as a definition")


def mask_comments_and_strings(text: str) -> str:
    result = list(text)
    index = 0
    while index < len(text):
        if text.startswith("//", index):
            end = text.find("\n", index)
            end = len(text) if end == -1 else end
            blank_range(result, index, end)
            index = end
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = len(text) - 2 if end == -1 else end
            blank_range(result, index, end + 2)
            index = end + 2
        elif text[index] in {'"', "'"}:
            quote = text[index]
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == quote:
                    index += 1
                    break
                if text[index] != "\n":
                    result[index] = " "
                index += 1
        else:
            index += 1
    return "".join(result)


def blank_range(chars: list[str], start: int, end: int) -> None:
    for idx in range(start, min(end, len(chars))):
        if chars[idx] != "\n":
            chars[idx] = " "


def find_matching(text: str, open_index: int, open_char: str, close_char: str) -> int | None:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
    return None


def find_signature_start(masked: str, name_start: int) -> int | None:
    index = name_start - 1
    while index >= 0 and masked[index].isspace():
        index -= 1
    while index >= 0 and masked[index] not in "{};":
        index -= 1
    return skip_whitespace(masked, index + 1)


def skip_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def parse_signature(signature: str, function_name: str) -> dict[str, Any]:
    match = re.match(rf"(?P<return_type>.+?)\b{re.escape(function_name)}\s*\((?P<params>.*)\)\s*$", signature, re.S)
    if not match:
        raise SystemExit(f"could not parse signature for {function_name!r}")
    return_type = " ".join(match.group("return_type").split())
    params = parse_parameters(match.group("params"))
    return {"return_type": return_type, "parameters": params}


def parse_parameters(params_text: str) -> list[dict[str, str]]:
    stripped = params_text.strip()
    if not stripped or stripped == "void":
        return []
    parameters: list[dict[str, str]] = []
    for raw in split_top_level_commas(stripped):
        declaration = " ".join(raw.strip().split())
        name_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?$", declaration)
        if name_match:
            name = name_match.group(1)
            c_type = declaration[: name_match.start(1)].strip()
        else:
            name = f"arg{len(parameters)}"
            c_type = declaration
        c_type = normalize_pointer_type(c_type)
        parameters.append({"name": name, "c_type": c_type, "direction": parameter_direction(c_type)})
    return parameters


def split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def normalize_pointer_type(c_type: str) -> str:
    return re.sub(r"\s*\*\s*", "*", c_type).strip()


def parameter_direction(c_type: str) -> str:
    if "*" not in c_type:
        return "input"
    if c_type.startswith("const ") or " const*" in c_type:
        return "input"
    return "inout"


def direct_type_dependencies(return_type: str, parameters: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    dependencies: list[dict[str, str]] = []
    for c_type in [return_type, *(param["c_type"] for param in parameters)]:
        clean = c_type.replace("*", "").replace("const", "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            dependencies.append({"kind": "type", "name": clean, "source": "extracted_signature"})
    return dependencies


def normalize_relative_path(path: Path) -> str:
    if path.is_absolute():
        raise SystemExit("--source-file must be relative to --repo-root")
    return path.as_posix()


def ensure_inside_root(root: Path, path: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"source file escapes repo root: {path}") from exc


def git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN_SOURCE_COMMIT"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rust_module_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name).lower()


if __name__ == "__main__":
    raise SystemExit(main())
