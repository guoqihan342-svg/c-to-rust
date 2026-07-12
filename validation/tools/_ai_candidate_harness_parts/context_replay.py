from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

from .context_security import atomic_write_bytes, redact_metadata_text, resolve_under, sha256_bytes
from validation.tools.replay_call_plan import (
    replay_call_plan_marker,
    validate_replay_call_plan,
)


MAX_REPLAY_SOURCE_BYTES = 64 * 1024
RUST_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_replay_api_contract(
    replay_test_path: Path | None,
    *,
    function_name: str,
    trusted_root: Path,
    expected_filename: str,
    known_roots: Iterable[str] = (),
    call_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    has_structured_call_plan = isinstance(call_plan, dict) and call_plan.get("status") == "bound"
    has_structured_contract = isinstance(call_plan, dict) and call_plan.get("status") in {
        "bound",
        "blocked",
    }
    api_name = str(call_plan.get("api_name")) if has_structured_call_plan else function_name
    base = {
        "schema_version": 2 if has_structured_contract else 1,
        "contract_kind": "generated_replay_rust_source",
        "function_name": function_name,
        "api_name": api_name,
    }
    if replay_test_path is None:
        return {**base, "status": "missing"}
    if not RUST_IDENTIFIER_RE.fullmatch(function_name) or not RUST_IDENTIFIER_RE.fullmatch(api_name):
        return {**base, "status": "blocked_invalid_function_identifier"}
    try:
        if (
            replay_test_path.name != expected_filename
            or not trusted_root.is_dir()
            or replay_test_path.parent.resolve() != trusted_root.resolve()
        ):
            return {**base, "status": "blocked_replay_source_path"}
        if replay_test_path.is_symlink() or not replay_test_path.is_file():
            return {**base, "status": "blocked_replay_source_missing"}
        size = replay_test_path.stat().st_size
        if size > MAX_REPLAY_SOURCE_BYTES:
            return {**base, "status": "blocked_replay_source_too_large"}
        data = replay_test_path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            return {**base, "status": "blocked_replay_source_unreadable"}
        source = data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return {**base, "status": "blocked_replay_source_unreadable"}
    sanitized = redact_metadata_text(source, known_roots)
    if sanitized != source:
        return {
            **base,
            "status": "blocked_replay_source_sensitive",
            "source_sha256": sha256_bytes(data),
        }
    if has_structured_contract and not has_structured_call_plan:
        return {
            **base,
            "status": "blocked_replay_call_plan_invalid",
            "source_sha256": sha256_bytes(data),
            "call_plan": call_plan,
        }
    bound_call_plan = None
    if has_structured_call_plan:
        try:
            validate_replay_call_plan(call_plan)
        except ValueError:
            return {
                **base,
                "status": "blocked_replay_call_plan_invalid",
                "source_sha256": sha256_bytes(data),
            }
        if replay_call_plan_marker(call_plan).rstrip("\n") not in source:
            return {
                **base,
                "status": "blocked_replay_call_plan_mismatch",
                "source_sha256": sha256_bytes(data),
            }
        bound_call_plan = call_plan
    call_count = count_rust_function_calls(source, api_name)
    if call_count < 1:
        return {
            **base,
            "status": "blocked_replay_call_missing",
            "source_sha256": sha256_bytes(data),
        }
    if bound_call_plan is not None and any(
        arity != len(bound_call_plan["parameters"])
        for arity in rust_function_call_arities(source, api_name)
    ):
        return {
            **base,
            "status": "blocked_replay_call_plan_mismatch",
            "source_sha256": sha256_bytes(data),
        }
    contract = {
        **base,
        "status": "bound",
        "call_count": call_count,
        "source": {
            "path": replay_test_path.name,
            "sha256": sha256_bytes(data),
            "size_bytes": len(data),
            "content": source,
        },
        "requirements": {
            "candidate_defines_function": True,
            "all_call_sites_typecheck": True,
            "parameter_count_and_order": "as_invoked_by_generated_replay",
            "return_type": "as_constrained_by_generated_replay",
        },
    }
    if bound_call_plan is not None:
        contract["call_plan"] = bound_call_plan
    return contract


def replay_contract_input_binding(contract: Any) -> dict[str, Any] | None:
    source = contract.get("source") if isinstance(contract, dict) else None
    if not isinstance(source, dict) or contract.get("status") != "bound":
        return None
    return {
        "kind": "generated_replay_contract",
        "path": source.get("path"),
        "sha256": source.get("sha256"),
        "size_bytes": source.get("size_bytes"),
    }


def materialize_replay_api_contract(context_pack: dict[str, Any], out_dir: Path) -> None:
    contract = context_pack.get("replay_api_contract")
    source = contract.get("source") if isinstance(contract, dict) else None
    if not isinstance(source, dict) or contract.get("status") != "bound":
        return
    path = resolve_under(out_dir, str(source.get("path") or ""))
    content = source.get("content")
    if not isinstance(content, str):
        raise ValueError("replay API contract source content is missing")
    data = content.encode("utf-8")
    if sha256_bytes(data) != source.get("sha256") or len(data) != source.get("size_bytes"):
        raise ValueError("replay API contract source binding drifted")
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            raise ValueError("replay API contract destination drifted")
        return
    atomic_write_bytes(path, data)


def validate_replay_api_contract_binding(context_pack: Any, context_path: Path) -> str:
    if not isinstance(context_pack, dict) or context_pack.get("schema_version") != 4:
        return "invalid_context_shape"
    contract = context_pack.get("replay_api_contract")
    if not isinstance(contract, dict) or contract.get("status") != "bound":
        return contract.get("status", "invalid") if isinstance(contract, dict) else "invalid"
    source = contract.get("source")
    if not isinstance(source, dict):
        return "invalid"
    api_name = contract.get("api_name", contract.get("function_name"))
    if not isinstance(api_name, str):
        return "invalid"
    expected_path = f"l3-{context_pack.get('slice_id')}-rust-replay-test-draft.rs"
    if (
        contract.get("function_name") != context_pack.get("function_name")
        or source.get("path") != expected_path
    ):
        return "binding_mismatch"
    try:
        path = resolve_under(context_path.parent, str(source.get("path") or ""))
        if path.is_symlink() or not path.is_file():
            return "binding_unreadable"
        data = path.read_bytes()
        content = data.decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return "binding_unreadable"
    call_plan = contract.get("call_plan")
    if isinstance(call_plan, dict):
        try:
            validate_replay_call_plan(call_plan)
        except ValueError:
            return "binding_mismatch"
        if (
            call_plan.get("source_function_name") != context_pack.get("function_name")
            or call_plan.get("api_name") != contract.get("api_name")
            or replay_call_plan_marker(call_plan).rstrip("\n") not in content
            or any(
                arity != len(call_plan["parameters"])
                for arity in rust_function_call_arities(content, str(call_plan["api_name"]))
            )
        ):
            return "binding_mismatch"
    if (
        len(data) != source.get("size_bytes")
        or sha256_bytes(data) != source.get("sha256")
        or content != source.get("content")
        or count_rust_function_calls(content, api_name)
        != contract.get("call_count")
    ):
        return "binding_mismatch"
    return "bound"


def count_rust_function_calls(source: str, function_name: str) -> int:
    if not RUST_IDENTIFIER_RE.fullmatch(function_name):
        return 0
    count = 0
    index = 0
    length = len(source)
    block_depth = 0
    previous_identifier: str | None = None
    target_definition_found = False
    while index < length:
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            block_depth = 1
            index += 2
            while index < length and block_depth:
                if source.startswith("/*", index):
                    block_depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    block_depth -= 1
                    index += 2
                else:
                    index += 1
            continue
        raw_end = raw_string_end(source, index)
        if raw_end is not None:
            index = raw_end
            continue
        if source[index] == "'" and index + 1 < length and (
            source[index + 1].isalpha() or source[index + 1] == "_"
        ):
            index += 2
            while index < length and (source[index].isalnum() or source[index] == "_"):
                index += 1
            continue
        if source[index] in {'"', "'"}:
            index = quoted_end(source, index, source[index])
            continue
        if source[index].isalpha() or source[index] == "_":
            end = index + 1
            while end < length and (source[end].isalnum() or source[end] == "_"):
                end += 1
            token = source[index:end]
            cursor = end
            while cursor < length and source[cursor].isspace():
                cursor += 1
            if token == function_name:
                if previous_identifier == "fn":
                    target_definition_found = True
                else:
                    qualifier = index - 1
                    while qualifier >= 0 and source[qualifier].isspace():
                        qualifier -= 1
                    qualified = qualifier >= 0 and source[qualifier] in {".", ":"}
                    if not qualified and cursor < length and source[cursor] == "(":
                        count += 1
            previous_identifier = token
            index = end
            continue
        index += 1
    return 0 if target_definition_found else count


def rust_function_call_arities(source: str, function_name: str) -> list[int]:
    if not RUST_IDENTIFIER_RE.fullmatch(function_name):
        return []
    code = rust_code_projection(source)
    if re.search(rf"\bfn\s+{re.escape(function_name)}\s*\(", code):
        return []
    arities: list[int] = []
    for match in re.finditer(rf"\b{re.escape(function_name)}\s*\(", code):
        qualifier = match.start() - 1
        while qualifier >= 0 and code[qualifier].isspace():
            qualifier -= 1
        if qualifier >= 0 and code[qualifier] in {".", ":"}:
            continue
        open_index = code.find("(", match.start(), match.end())
        close_index, arity = call_arity(code, open_index)
        if close_index is not None:
            arities.append(arity)
    return arities


def call_arity(code: str, open_index: int) -> tuple[int | None, int]:
    paren_depth = 1
    bracket_depth = 0
    brace_depth = 0
    commas = 0
    has_token = False
    index = open_index + 1
    while index < len(code):
        char = code[index]
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
            if paren_depth == 0:
                return index, 0 if not has_token else commas + 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]" and bracket_depth:
            bracket_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}" and brace_depth:
            brace_depth -= 1
        elif (
            char == ","
            and paren_depth == 1
            and bracket_depth == 0
            and brace_depth == 0
        ):
            commas += 1
        elif not char.isspace() and paren_depth == 1:
            has_token = True
        index += 1
    return None, 0


def rust_code_projection(source: str) -> str:
    projected = list(source)
    index = 0
    while index < len(source):
        if source.startswith("//", index):
            end = source.find("\n", index + 2)
            end = len(source) if end < 0 else end
        elif source.startswith("/*", index):
            depth = 1
            end = index + 2
            while end < len(source) and depth:
                if source.startswith("/*", end):
                    depth += 1
                    end += 2
                elif source.startswith("*/", end):
                    depth -= 1
                    end += 2
                else:
                    end += 1
        else:
            raw_end = raw_string_end(source, index)
            if raw_end is not None:
                end = raw_end
            elif source[index] == "'" and index + 1 < len(source) and (
                source[index + 1].isalpha() or source[index + 1] == "_"
            ):
                index += 1
                continue
            elif source[index] in {'"', "'"}:
                end = quoted_end(source, index, source[index])
            else:
                index += 1
                continue
        for masked in range(index, end):
            if projected[masked] not in {"\r", "\n"}:
                projected[masked] = " "
        index = end
    return "".join(projected)


def quoted_end(source: str, start: int, quote: str) -> int:
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
        elif source[index] == quote:
            return index + 1
        else:
            index += 1
    return len(source)


def raw_string_end(source: str, start: int) -> int | None:
    if source[start] != "r":
        return None
    cursor = start + 1
    while cursor < len(source) and source[cursor] == "#":
        cursor += 1
    if cursor >= len(source) or source[cursor] != '"':
        return None
    hashes = source[start + 1 : cursor]
    terminator = '"' + hashes
    end = source.find(terminator, cursor + 1)
    return len(source) if end < 0 else end + len(terminator)


__all__ = [
    "MAX_REPLAY_SOURCE_BYTES",
    "build_replay_api_contract",
    "count_rust_function_calls",
    "materialize_replay_api_contract",
    "replay_contract_input_binding",
    "rust_function_call_arities",
    "validate_replay_api_contract_binding",
]
