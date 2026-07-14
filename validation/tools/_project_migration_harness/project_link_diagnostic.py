from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .artifacts import content_sha256
from .project_diagnostic_shape import build_project_diagnostic


LINK_DIAGNOSTIC_CODE = "linker-undefined-symbol"
_LINK_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
_OWNER_FIELDS = (
    ("public_api", "symbol", "declaration_id"),
    ("global_ownership", "symbol", "declaration_id"),
    ("initialization", "function", "init_id"),
)


def project_link_diagnostic(
    value: Mapping[str, Any], gate_kind: str, rust_project_ir: Mapping[str, Any],
) -> tuple[dict[str, Any], str | None]:
    symbol = value.get("linker_symbol")
    message = value.get("message")
    if (
        not isinstance(symbol, str) or _LINK_SYMBOL.fullmatch(symbol) is None
        or not isinstance(message, str) or not message
    ):
        return {}, "link-diagnostic-invalid"
    owner = _unique_symbol_owner(symbol, rust_project_ir)
    if owner is None:
        return {}, "link-symbol-not-project-unique"
    entity_ids, module_ids = owner
    event_sha = content_sha256({
        "source_code": LINK_DIAGNOSTIC_CODE,
        "stage": gate_kind, "symbol": symbol,
    })
    diagnostic = build_project_diagnostic(
        code=f"project-verifier-{LINK_DIAGNOSTIC_CODE}",
        entity_ids=sorted({
            LINK_DIAGNOSTIC_CODE, f"event:{event_sha}",
            f"link-symbol:{symbol}", *entity_ids, *module_ids,
        }),
        affected_module_ids=module_ids,
    )
    return {
        "family": "link", "source_code": LINK_DIAGNOSTIC_CODE,
        "stage": gate_kind, "message": message[:512],
        "location": {"file": None, "line": None, "column": None},
        "project_diagnostic": diagnostic,
    }, None


def _unique_symbol_owner(
    symbol: str, rust_project_ir: Mapping[str, Any],
) -> tuple[list[str], list[str]] | None:
    known_modules = {
        str(item.get("module_id")) for item in rust_project_ir.get("modules", [])
        if isinstance(item, Mapping) and isinstance(item.get("module_id"), str)
    }
    entities: set[str] = set()
    owners: set[str] = set()
    for section, field, identity_field in _OWNER_FIELDS:
        for record in _records(rust_project_ir, section):
            if record.get(field) == symbol:
                identity = record.get(identity_field, symbol)
                module_id = record.get("module_id")
                if not isinstance(identity, str) or not isinstance(module_id, str):
                    return None
                entities.add(f"{section}:{identity}")
                owners.add(module_id)
    for record in _records(rust_project_ir, "ffi_boundaries"):
        if record.get("link_name") != symbol:
            continue
        if record.get("direction") != "export":
            return None
        identity = record.get("declaration_id", symbol)
        module_id = record.get("module_id")
        if not isinstance(identity, str) or not isinstance(module_id, str):
            return None
        entities.add(f"ffi_boundaries:{identity}")
        owners.add(module_id)
    if not entities or len(owners) != 1 or not owners.issubset(known_modules):
        return None
    return sorted(entities), sorted(owners)


def _records(
    rust_project_ir: Mapping[str, Any], section: str,
) -> list[Mapping[str, Any]]:
    values = rust_project_ir.get(section)
    return [item for item in values if isinstance(item, Mapping)] \
        if isinstance(values, list) else []


__all__ = ["LINK_DIAGNOSTIC_CODE", "project_link_diagnostic"]
