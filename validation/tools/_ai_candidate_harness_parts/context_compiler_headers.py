from __future__ import annotations

import json
import re
from typing import Any

from .context_security import sha256_bytes


C_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COMPILER_HEADER_PREFIX = "compiler-header:"


def is_compiler_header_candidate(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    source_ref = item.get("source_ref")
    has_namespace = (
        isinstance(source_ref, str)
        and source_ref.lower().startswith(COMPILER_HEADER_PREFIX)
    )
    return has_namespace or (
        item.get("definition_status") == "declared_external_direct_callee"
        and "header_files" in item
    )


def compiler_header_declaration(
    item: dict[str, Any],
    signatures: Any,
) -> dict[str, Any]:
    name = item.get("name")
    if not isinstance(name, str) or C_IDENTIFIER_RE.fullmatch(name) is None:
        raise ValueError("compiler_header_callee_name_invalid")
    if item.get("definition_status") != "declared_external_direct_callee":
        raise ValueError("compiler_header_definition_status_invalid")

    source_ref = item.get("source_ref")
    if not isinstance(source_ref, str) or not source_ref.startswith(COMPILER_HEADER_PREFIX):
        raise ValueError("compiler_header_namespace_invalid")
    reference = source_ref[len(COMPILER_HEADER_PREFIX):]
    if reference.count("#") != 1:
        raise ValueError("compiler_header_source_ref_invalid")
    header, symbol = reference.split("#", 1)
    if _relative_header(header) is None:
        raise ValueError("compiler_header_path_invalid")
    if symbol != name or C_IDENTIFIER_RE.fullmatch(symbol) is None:
        raise ValueError("compiler_header_symbol_mismatch")

    header_files = item.get("header_files")
    if not isinstance(header_files, list) or not header_files:
        raise ValueError("compiler_header_inventory_missing")
    normalized_headers = [_relative_header(value) for value in header_files]
    if any(value is None for value in normalized_headers):
        raise ValueError("compiler_header_inventory_invalid")
    inventory = [value for value in normalized_headers if value is not None]
    if len(set(inventory)) != len(inventory) or header not in inventory:
        raise ValueError("compiler_header_inventory_mismatch")

    signature_ref = item.get("signature_ref")
    if not isinstance(signature_ref, str) or not signature_ref:
        raise ValueError("compiler_header_signature_ref_missing")
    if not isinstance(signatures, list):
        raise ValueError("compiler_header_signature_inventory_missing")
    matching = [
        value
        for value in signatures
        if isinstance(value, dict) and value.get("id") == signature_ref
    ]
    if len(matching) != 1:
        raise ValueError("compiler_header_signature_ref_ambiguous")
    signature = matching[0]
    if (
        signature.get("role") != "external_direct_callee"
        or signature.get("function") != name
        or signature.get("definition_status") != "declared_external_direct_callee"
        or signature.get("source_ref") != source_ref
    ):
        raise ValueError("compiler_header_signature_mismatch")
    if item.get("stub_boundary") != "compile_only":
        raise ValueError("compiler_header_stub_boundary_invalid")

    declaration = {
        "schema_version": 1,
        "callee": name,
        "role": "compiler_header_declaration_only",
        "definition_status": "declared_external_direct_callee",
        "source_ref": source_ref,
        "header": header,
        "header_inventory": inventory,
        "signature_ref": signature_ref,
        "stub_boundary": "compile_only",
        "allowed_use": "compile_context_only",
        "execution_allowed": False,
        "semantics_verified": False,
    }
    declaration["declaration_sha256"] = sha256_bytes(_canonical_bytes(declaration))
    return declaration


def _relative_header(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("~"):
        return None
    if value.startswith("/") or ":" in value or "//" in value:
        return None
    parts = value.split("/")
    if any(
        not part
        or part in {".", ".."}
        or re.fullmatch(r"[A-Za-z0-9_.+-]+", part) is None
        for part in parts
    ):
        return None
    return "/".join(parts)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


__all__ = ["compiler_header_declaration", "is_compiler_header_candidate"]
