from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from typing import Any

from .rust_source_pre_cfg_coverage import validate_rust_source_pre_cfg_coverage
from .rust_source_pre_cfg_records import validate_rust_source_records


RUST_SOURCE_PRE_CFG_SCHEMA_VERSION = 1
MAX_RUST_SOURCE_BYTES = 4 * 1024 * 1024
MAX_RUST_WITNESS_OUTPUT_BYTES = 16 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TOP_KEYS = {
    "schema_version", "artifact_kind", "status", "parser", "source",
    "modules", "items", "signatures", "types", "globals", "initialization",
    "attributes", "macro_invocations", "blockers", "claim_boundary",
}
_PARSER = {
    "implementation": "syn",
    "version": "2.0.118",
    "quote_version": "1.0.46",
    "protocol_version": 1,
    "crate_version": "0.1.0",
}
_CLAIM_BOUNDARY = {
    "phase": "pre-cfg",
    "candidate_only": True,
    "post_cfg": False,
    "section_closure": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
_BLOCKER_CODES = {
    "rust_source_cfg_attr_unresolved",
    "rust_source_external_module_unresolved",
    "rust_source_fact_limit_exceeded",
    "rust_source_invalid_utf8",
    "rust_source_macro_expansion_required",
    "rust_source_module_depth_exceeded",
    "rust_source_no_items",
    "rust_source_output_limit_exceeded",
    "rust_source_parse_ambiguity",
    "rust_source_parse_failed",
    "rust_source_size_limit_exceeded",
    "rust_source_syntax_limit_exceeded",
    "rust_source_unsupported_attribute",
    "rust_source_unsupported_foreign_item",
    "rust_source_unsupported_impl_item",
    "rust_source_unsupported_item",
    "rust_source_unsupported_trait_item",
}


def parse_rust_source_pre_cfg_witness(
    raw_output: bytes,
    source: bytes,
) -> dict[str, Any]:
    if (
        not isinstance(raw_output, bytes)
        or not raw_output
        or len(raw_output) > MAX_RUST_WITNESS_OUTPUT_BYTES
        or not raw_output.endswith(b"\n")
    ):
        _fail("rust_source_pre_cfg_raw_output_invalid")
    try:
        value = json.loads(
            raw_output.decode("utf-8"), object_pairs_hook=_unique_object,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("rust_source_pre_cfg_raw_output_invalid") from error
    return validate_rust_source_pre_cfg_witness(value, source)


def validate_rust_source_pre_cfg_witness(
    value: Any,
    source: bytes,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        _fail("rust_source_pre_cfg_schema_invalid")
    witness = dict(value)
    if (
        witness.get("schema_version") != RUST_SOURCE_PRE_CFG_SCHEMA_VERSION
        or witness.get("artifact_kind") != "rust-source-pre-cfg-witness"
        or witness.get("parser") != _PARSER
        or witness.get("claim_boundary") != _CLAIM_BOUNDARY
    ):
        _fail("rust_source_pre_cfg_identity_invalid")
    _source_identity(witness.get("source"), source)
    record_sets = validate_rust_source_records(witness)
    validate_rust_source_pre_cfg_coverage(witness)
    if sum(len(witness[key]) for key in (
        "modules", "items", "signatures", "types", "globals",
        "initialization", "attributes", "macro_invocations",
    )) > 20_000:
        _fail("rust_source_pre_cfg_fact_limit_invalid")
    blockers = _blockers(witness.get("blockers"), record_sets["items"])
    expected_status = "blocked" if blockers else "ready"
    if witness.get("status") != expected_status:
        _fail("rust_source_pre_cfg_status_invalid")
    if expected_status == "ready" and (
        not witness["modules"] or not witness["items"]
    ):
        _fail("rust_source_pre_cfg_ready_coverage_invalid")
    _cross_validate(witness, blockers)
    return witness


def _source_identity(value: Any, source: bytes) -> None:
    if not isinstance(source, bytes):
        _fail("rust_source_pre_cfg_source_bytes_invalid")
    if not isinstance(value, Mapping) or set(value) != {
        "sha256", "size_bytes", "encoding",
    }:
        _fail("rust_source_pre_cfg_source_identity_invalid")
    try:
        source.decode("utf-8")
        encoding = "utf-8"
    except UnicodeError:
        encoding = "invalid-utf-8"
    if len(source) > MAX_RUST_SOURCE_BYTES:
        encoding = "not-inspected"
    if (
        value.get("size_bytes") != len(source)
        or value.get("sha256") != hashlib.sha256(source).hexdigest()
        or value.get("encoding") != encoding
    ):
        _fail("rust_source_pre_cfg_source_binding_invalid")


def _blockers(value: Any, items: set[str]) -> set[tuple[Any, ...]]:
    if not isinstance(value, list) or len(value) > 4_096:
        _fail("rust_source_pre_cfg_blockers_invalid")
    result: set[tuple[Any, ...]] = set()
    ordered = []
    for blocker in value:
        if not isinstance(blocker, Mapping) or set(blocker) != {
            "code", "item_id", "detail_sha256",
        }:
            _fail("rust_source_pre_cfg_blocker_schema_invalid")
        code = blocker.get("code")
        item_id = blocker.get("item_id")
        detail = blocker.get("detail_sha256")
        if (
            code not in _BLOCKER_CODES
            or (
                item_id is not None
                and item_id != "crate-root"
                and item_id not in items
            )
            or (detail is not None and not _is_sha(detail))
        ):
            _fail("rust_source_pre_cfg_blocker_invalid")
        identity = (code, item_id, detail)
        if identity in result:
            _fail("rust_source_pre_cfg_blocker_duplicate")
        result.add(identity)
        ordered.append(identity)
    if ordered != sorted(ordered, key=_blocker_sort_key):
        _fail("rust_source_pre_cfg_blockers_noncanonical")
    return result


def _cross_validate(
    witness: Mapping[str, Any], blockers: set[tuple[Any, ...]],
) -> None:
    for attribute in witness["attributes"]:
        expected = {
            "cfg_attr": "rust_source_cfg_attr_unresolved",
            "derive": "rust_source_macro_expansion_required",
            "unsupported": "rust_source_unsupported_attribute",
        }.get(attribute["kind"])
        if expected and (
            expected, attribute["item_id"], attribute["syntax_sha256"],
        ) not in blockers:
            _fail("rust_source_pre_cfg_attribute_blocker_missing")
    for invocation in witness["macro_invocations"]:
        if (
            "rust_source_macro_expansion_required",
            invocation["item_id"], invocation["syntax_sha256"],
        ) not in blockers:
            _fail("rust_source_pre_cfg_macro_blocker_missing")
    item_by_path = {
        item["item_path"]: item["item_id"]
        for item in witness["items"] if item["kind"] == "module"
    }
    for module in witness["modules"]:
        if module["kind"] == "external":
            item_id = item_by_path.get(module["module_path"])
            if item_id is None or (
                "rust_source_external_module_unresolved", item_id, None,
            ) not in blockers:
                _fail("rust_source_pre_cfg_external_module_blocker_missing")


def _unique_object(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in items:
        if key in result:
            _fail("rust_source_pre_cfg_duplicate_json_key")
        result[key] = value
    return result


def _blocker_sort_key(value: tuple[Any, ...]) -> tuple[Any, ...]:
    return (
        value[0], (0, "") if value[1] is None else (1, value[1]),
        (0, "") if value[2] is None else (1, value[2]),
    )


def _is_sha(value: Any) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _fail(code: str) -> None:
    raise ValueError(code)


__all__ = [
    "MAX_RUST_SOURCE_BYTES", "MAX_RUST_WITNESS_OUTPUT_BYTES",
    "RUST_SOURCE_PRE_CFG_SCHEMA_VERSION",
    "parse_rust_source_pre_cfg_witness",
    "validate_rust_source_pre_cfg_witness",
]
