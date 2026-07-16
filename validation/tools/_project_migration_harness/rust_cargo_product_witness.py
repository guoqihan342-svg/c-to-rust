from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .cargo_compiler_artifact_evidence import (
    validate_cargo_compiler_artifact_evidence,
)
from .rust_cargo_topology_ir import validate_rust_cargo_topology_expectation
from .rust_link_product_inspection import inspect_rust_link_product
from .rust_product_evidence import (
    read_rust_product, validate_rust_product_evidence,
)


_PACKAGE_SUFFIX = re.compile(
    r"(?P<name>[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})@"
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.+_-]{0,127})\Z",
    re.ASCII,
)
_CLAIM_BOUNDARY = {
    "section_closure": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}


def build_rust_cargo_product_witness(
    ledger_path: Path, products: Any, compiler_evidence: Mapping[str, Any],
    topology_expectation: Mapping[str, Any],
) -> dict[str, Any]:
    compiler = validate_cargo_compiler_artifact_evidence(compiler_evidence)
    expectation = validate_rust_cargo_topology_expectation(
        topology_expectation,
    )
    normalized = _products(products)
    blockers: list[dict[str, str]] = []
    inspections = []
    for product in normalized:
        try:
            data = read_rust_product(ledger_path, product)
            inspection = inspect_rust_link_product(
                data, product["product_kind"],
            )
        except ValueError:
            blockers.append(_block(
                "rust_cargo_product_inspection_invalid", _identity(product),
            ))
        else:
            inspections.append({
                "product_sha256": product["product_sha256"],
                "inspection": inspection,
            })
    expected = _expected_identities(expectation)
    actual = {_identity(item) for item in normalized}
    for identity in sorted(expected - actual):
        blockers.append(_block("rust_cargo_product_missing", identity))
    for identity in sorted(actual - expected):
        blockers.append(_block("rust_cargo_product_undeclared", identity))
    bindings = _compiler_bindings(compiler)
    for product in normalized:
        identity = _identity(product)
        if product["package"]["package_id_sha256"] not in bindings.get(
            identity[:3], set(),
        ):
            blockers.append(_block(
                "rust_cargo_product_compiler_binding_mismatch", identity,
            ))
    blockers = sorted(blockers, key=canonical_json_bytes)
    core = {
        "schema_version": 1,
        "artifact_kind": "rust-cargo-final-product-witness",
        "status": "blocked" if blockers else "ready",
        "products": normalized,
        "product_set_sha256": content_sha256(normalized),
        "inspections": inspections,
        "inspection_set_sha256": content_sha256(inspections),
        "coverage": {
            "expected_product_count": len(expected),
            "observed_product_count": len(actual),
            "inspected_product_count": len(inspections),
            "final_product_coverage_complete": (
                not blockers and len(inspections) == len(normalized)
            ),
        },
        "blockers": blockers,
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return {**core, "witness_sha256": content_sha256(core)}


def _products(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("rust_cargo_product_witness_products_invalid")
    normalized = [validate_rust_product_evidence(item) for item in value]
    ordered = sorted(normalized, key=canonical_json_bytes)
    identities = [_identity(item) for item in ordered]
    if normalized != ordered or len(identities) != len(set(identities)):
        raise ValueError("rust_cargo_product_witness_products_not_canonical")
    return ordered


def _expected_identities(
    expectation: Mapping[str, Any],
) -> set[tuple[str, str, str, str]]:
    result = set()
    for package in expectation["facts"]["packages"]:
        for target in package["targets"]:
            for kind in _product_kinds(target["crate_types"]):
                result.add((
                    package["name"], package["version"], target["name"], kind,
                ))
    return result


def _compiler_bindings(
    compiler: Mapping[str, Any],
) -> dict[tuple[str, str, str], set[str]]:
    result: dict[tuple[str, str, str], set[str]] = {}
    for artifact in compiler["artifacts"]:
        match = _PACKAGE_SUFFIX.search(artifact["package_id"])
        if match is None:
            continue
        key = (
            match.group("name"), match.group("version"),
            artifact["target"]["name"],
        )
        result.setdefault(key, set()).add(hashlib.sha256(
            artifact["package_id"].encode("utf-8"),
        ).hexdigest())
    return result


def _product_kinds(crate_types: list[str]) -> list[str]:
    result = set(crate_types) & {"bin", "cdylib", "rlib", "staticlib"}
    if "lib" in crate_types and "rlib" not in result:
        result.add("rlib")
    return sorted(result)


def _identity(value: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(value["package"]["name"]), str(value["package"]["version"]),
        str(value["target"]["name"]), str(value["product_kind"]),
    )


def _block(
    code: str, identity: tuple[str, str, str, str],
) -> dict[str, str]:
    return {"code": code, "detail": content_sha256(list(identity))}


__all__ = ["build_rust_cargo_product_witness"]
