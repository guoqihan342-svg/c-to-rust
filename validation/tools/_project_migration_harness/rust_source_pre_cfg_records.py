from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from typing import Any


_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MODULE_ID = re.compile(r"module-[0-9]{6}\Z", re.ASCII)
_ITEM_ID = re.compile(r"item-[0-9]{6}\Z", re.ASCII)
_FACT_ID = re.compile(r"(?:attribute|macro)-[0-9]{6}\Z", re.ASCII)
_ITEM_KINDS = {
    "const", "extern-crate", "foreign-function", "foreign-macro",
    "foreign-module", "foreign-static", "foreign-type", "function", "impl",
    "impl-const", "impl-function", "impl-macro", "impl-type", "macro",
    "module", "static", "struct", "enum", "union", "trait", "trait-alias",
    "trait-const", "trait-function", "trait-macro", "trait-type", "type-alias",
    "use",
}
_SIGNATURE_KINDS = {
    "function", "foreign-function", "impl-function", "trait-function",
}
_TYPE_KINDS = {
    "associated-type", "enum", "foreign-type", "struct", "trait",
    "trait-alias", "type-alias", "union",
}
_GLOBAL_KINDS = {"associated-const", "const", "foreign-static", "static"}
_INIT_KINDS = {
    "const-initializer", "drop-impl", "global-initializer",
    "static-initializer",
}


def validate_rust_source_records(value: Mapping[str, Any]) -> dict[str, set[str]]:
    modules = _modules(value.get("modules"))
    items = _items(value.get("items"), modules)
    _signatures(value.get("signatures"), items)
    _types(value.get("types"), items)
    _globals(value.get("globals"), items)
    _initialization(value.get("initialization"), items)
    attribute_ids = _attributes(value.get("attributes"), items)
    macro_ids = _macros(value.get("macro_invocations"), items)
    return {
        "modules": modules,
        "items": items,
        "facts": attribute_ids | macro_ids,
    }


def _modules(value: Any) -> set[str]:
    records = _list(value, "modules")
    identifiers: set[str] = set()
    for index, record in enumerate(records):
        _keys(record, {"module_id", "parent_module_id", "module_path", "kind"})
        identifier = _identifier(record["module_id"], _MODULE_ID, "module")
        if identifier != f"module-{index:06d}" or identifier in identifiers:
            _fail("rust_source_pre_cfg_module_identity_invalid")
        identifiers.add(identifier)
        _logical_path(record["module_path"])
        parent = record["parent_module_id"]
        if index == 0:
            if record != {
                "module_id": "module-000000", "parent_module_id": None,
                "module_path": "crate", "kind": "root",
            }:
                _fail("rust_source_pre_cfg_root_module_invalid")
        elif (
            record["kind"] not in {"inline", "external"}
            or parent not in identifiers
        ):
            _fail("rust_source_pre_cfg_module_parent_invalid")
    return identifiers


def _items(value: Any, modules: set[str]) -> set[str]:
    records = _list(value, "items")
    identifiers: set[str] = set()
    for index, record in enumerate(records):
        _keys(record, {
            "item_id", "module_id", "item_path", "name", "kind", "visibility",
        })
        identifier = _identifier(record["item_id"], _ITEM_ID, "item")
        if identifier != f"item-{index:06d}" or identifier in identifiers:
            _fail("rust_source_pre_cfg_item_identity_invalid")
        identifiers.add(identifier)
        if record["module_id"] not in modules or record["kind"] not in _ITEM_KINDS:
            _fail("rust_source_pre_cfg_item_reference_invalid")
        _logical_path(record["item_path"])
        _optional_text(record["name"])
        _text(record["visibility"], 512)
    return identifiers


def _signatures(value: Any, items: set[str]) -> None:
    for record in _list(value, "signatures"):
        _keys(record, {
            "item_id", "kind", "syntax", "syntax_sha256", "syntax_size_bytes",
            "abi", "is_unsafe", "is_async", "is_const", "is_variadic",
        })
        _item_reference(record["item_id"], items)
        if record["kind"] not in _SIGNATURE_KINDS:
            _fail("rust_source_pre_cfg_signature_kind_invalid")
        _syntax(record, "syntax", "syntax_sha256", "syntax_size_bytes")
        _optional_text(record["abi"])
        _booleans(record, "is_unsafe", "is_async", "is_const", "is_variadic")


def _types(value: Any, items: set[str]) -> None:
    for record in _list(value, "types"):
        _keys(record, {
            "item_id", "kind", "syntax", "syntax_sha256", "syntax_size_bytes",
            "field_count", "variant_count",
        })
        _item_reference(record["item_id"], items)
        if record["kind"] not in _TYPE_KINDS:
            _fail("rust_source_pre_cfg_type_kind_invalid")
        _syntax(record, "syntax", "syntax_sha256", "syntax_size_bytes")
        if not _count(record["field_count"]) or not _count(record["variant_count"]):
            _fail("rust_source_pre_cfg_type_count_invalid")


def _globals(value: Any, items: set[str]) -> None:
    for record in _list(value, "globals"):
        _keys(record, {
            "item_id", "kind", "type_syntax", "type_sha256", "type_size_bytes",
            "mutable", "has_initializer",
        })
        _item_reference(record["item_id"], items)
        if record["kind"] not in _GLOBAL_KINDS:
            _fail("rust_source_pre_cfg_global_kind_invalid")
        _syntax(record, "type_syntax", "type_sha256", "type_size_bytes")
        _booleans(record, "mutable", "has_initializer")


def _initialization(value: Any, items: set[str]) -> None:
    for record in _list(value, "initialization"):
        _keys(record, {
            "item_id", "kind", "expression_sha256", "expression_size_bytes",
            "order",
        })
        _item_reference(record["item_id"], items)
        digest, size = record["expression_sha256"], record["expression_size_bytes"]
        if (
            record["kind"] not in _INIT_KINDS
            or record["order"] != "unresolved-pre-cfg"
            or (digest is None) != (size is None)
            or (digest is not None and (not _sha(digest) or not _count(size)))
        ):
            _fail("rust_source_pre_cfg_initialization_invalid")


def _attributes(value: Any, items: set[str]) -> set[str]:
    identifiers: set[str] = set()
    policy = {
        "cfg": (True, False), "cfg_attr": (False, True),
        "derive": (False, True), "builtin": (True, False),
        "unsupported": (False, False),
    }
    for record in _list(value, "attributes"):
        _keys(record, {
            "fact_id", "item_id", "path", "kind", "syntax", "syntax_sha256",
            "syntax_size_bytes", "supported_pre_cfg", "requires_expansion",
        })
        identifier = _fact_reference(record["fact_id"], identifiers)
        identifiers.add(identifier)
        _owner_reference(record["item_id"], items)
        _text(record["path"], 512)
        _syntax(record, "syntax", "syntax_sha256", "syntax_size_bytes")
        expected = policy.get(record["kind"])
        if expected != (
            record["supported_pre_cfg"], record["requires_expansion"],
        ):
            _fail("rust_source_pre_cfg_attribute_policy_invalid")
        if record["kind"] in {"cfg", "cfg_attr", "derive"} and (
            record["path"] != record["kind"]
        ):
            _fail("rust_source_pre_cfg_attribute_path_invalid")
    return identifiers


def _macros(value: Any, items: set[str]) -> set[str]:
    identifiers: set[str] = set()
    for record in _list(value, "macro_invocations"):
        _keys(record, {
            "fact_id", "item_id", "path", "syntax_sha256", "syntax_size_bytes",
        })
        identifier = _fact_reference(record["fact_id"], identifiers)
        identifiers.add(identifier)
        _owner_reference(record["item_id"], items)
        _text(record["path"], 512)
        if not _sha(record["syntax_sha256"]) or not _count(record["syntax_size_bytes"]):
            _fail("rust_source_pre_cfg_macro_invalid")
    return identifiers


def _syntax(record: Mapping[str, Any], text: str, digest: str, size: str) -> None:
    value = _text(record[text], 64 * 1024)
    if (
        record[size] != len(value.encode("utf-8"))
        or record[digest] != hashlib.sha256(value.encode("utf-8")).hexdigest()
    ):
        _fail("rust_source_pre_cfg_syntax_binding_invalid")


def _keys(value: Any, expected: set[str]) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        _fail("rust_source_pre_cfg_record_schema_invalid")


def _list(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) > 20_000:
        _fail(f"rust_source_pre_cfg_{label}_invalid")
    return value


def _text(value: Any, maximum: int) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > maximum:
        _fail("rust_source_pre_cfg_text_invalid")
    return value


def _optional_text(value: Any) -> None:
    if value is not None:
        _text(value, 512)


def _logical_path(value: Any) -> None:
    text = _text(value, 4096)
    if not text.startswith("crate") or any(char in text for char in ("/", "\\", "\x00")):
        _fail("rust_source_pre_cfg_logical_path_invalid")


def _identifier(value: Any, pattern: re.Pattern[str], label: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(f"rust_source_pre_cfg_{label}_identity_invalid")
    return value


def _item_reference(value: Any, items: set[str]) -> None:
    if value not in items:
        _fail("rust_source_pre_cfg_item_reference_invalid")


def _owner_reference(value: Any, items: set[str]) -> None:
    if value != "crate-root" and value not in items:
        _fail("rust_source_pre_cfg_owner_reference_invalid")


def _fact_reference(value: Any, existing: set[str]) -> str:
    identifier = _identifier(value, _FACT_ID, "fact")
    if identifier in existing:
        _fail("rust_source_pre_cfg_fact_identity_invalid")
    return identifier


def _booleans(record: Mapping[str, Any], *keys: str) -> None:
    if any(type(record[key]) is not bool for key in keys):
        _fail("rust_source_pre_cfg_boolean_invalid")


def _count(value: Any) -> bool:
    return type(value) is int and 0 <= value <= 20_000_000


def _sha(value: Any) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _fail(code: str) -> None:
    raise ValueError(code)


__all__ = ["validate_rust_source_records"]
