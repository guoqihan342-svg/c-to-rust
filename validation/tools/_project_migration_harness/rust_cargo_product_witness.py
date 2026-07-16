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
from .rust_link_product_inspection import (
    inspect_rust_link_product, validate_rust_link_product_inspection,
)
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
_WITNESS_FIELDS = {
    "schema_version", "artifact_kind", "status", "products",
    "product_set_sha256", "inspections", "inspection_set_sha256", "coverage",
    "blockers", "claim_boundary", "witness_sha256",
}
_BINDING_FIELDS = {"product_sha256", "inspection_sha256", "inspection"}
_COVERAGE_FIELDS = {
    "expected_product_count", "observed_product_count",
    "inspected_product_count", "final_product_coverage_complete",
}
_BLOCK_CODES = {
    "rust_cargo_product_inspection_invalid", "rust_cargo_product_missing",
    "rust_cargo_product_undeclared",
    "rust_cargo_product_compiler_binding_mismatch",
}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


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
            binding = _inspection_binding(product, inspection)
        except ValueError:
            blockers.append(_block(
                "rust_cargo_product_inspection_invalid", _identity(product),
            ))
        else:
            inspections.append(binding)
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
        "schema_version": 2,
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
    return validate_rust_cargo_product_witness({
        **core, "witness_sha256": content_sha256(core),
    })


def validate_rust_cargo_product_witness(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _WITNESS_FIELDS:
        raise ValueError("rust_cargo_product_witness_schema_invalid")
    witness = dict(value)
    products = _products(witness.get("products"))
    inspections = _inspection_bindings(witness.get("inspections"), products)
    blockers = witness.get("blockers")
    coverage = witness.get("coverage")
    core = {key: witness[key] for key in witness if key != "witness_sha256"}
    blockers_valid = (
        isinstance(blockers, list)
        and all(
            isinstance(item, Mapping)
            and set(item) == {"code", "detail"}
            and isinstance(item.get("code"), str)
            and item.get("code") in _BLOCK_CODES
            and _sha256(item.get("detail"))
            for item in blockers
        )
        and blockers == sorted(blockers, key=canonical_json_bytes)
    )
    coverage_complete = blockers == [] and len(inspections) == len(products)
    if (
        witness.get("schema_version") != 2
        or witness.get("artifact_kind") != "rust-cargo-final-product-witness"
        or witness.get("status") != ("blocked" if blockers else "ready")
        or witness.get("products") != products
        or witness.get("product_set_sha256") != content_sha256(products)
        or witness.get("inspections") != inspections
        or witness.get("inspection_set_sha256") != content_sha256(inspections)
        or not blockers_valid
        or not isinstance(coverage, Mapping)
        or set(coverage) != _COVERAGE_FIELDS
        or type(coverage.get("expected_product_count")) is not int
        or coverage["expected_product_count"] < 0
        or coverage.get("observed_product_count") != len(products)
        or coverage.get("inspected_product_count") != len(inspections)
        or coverage.get("final_product_coverage_complete") is not coverage_complete
        or (not blockers and coverage["expected_product_count"] != len(products))
        or witness.get("claim_boundary") != _CLAIM_BOUNDARY
        or witness.get("witness_sha256") != content_sha256(core)
    ):
        raise ValueError("rust_cargo_product_witness_invalid")
    return {**core, "witness_sha256": witness["witness_sha256"]}


def reopen_rust_cargo_product_witness(
    ledger_path: Path, stored: Any, compiler_evidence: Mapping[str, Any],
    topology_expectation: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_rust_cargo_product_witness(stored)
    current = build_rust_cargo_product_witness(
        ledger_path, validated["products"], compiler_evidence,
        topology_expectation,
    )
    if current != validated:
        raise ValueError("rust_cargo_product_witness_reopen_drift")
    return current


def _inspection_binding(
    product: Mapping[str, Any], inspection: Any,
) -> dict[str, Any]:
    normalized = validate_rust_link_product_inspection(inspection)
    if (
        normalized["product_kind"] != product["product_kind"]
        or normalized["file_sha256"] != product["file"]["sha256"]
    ):
        raise ValueError("rust_cargo_product_witness_inspection_binding_invalid")
    return {
        "product_sha256": product["product_sha256"],
        "inspection_sha256": normalized["inspection_sha256"],
        "inspection": normalized,
    }


def _inspection_bindings(
    value: Any, products: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > len(products):
        raise ValueError("rust_cargo_product_witness_inspections_invalid")
    indexed = {
        product["product_sha256"]: (index, product)
        for index, product in enumerate(products)
    }
    previous = -1
    result = []
    for raw in value:
        digest = raw.get("product_sha256") if isinstance(raw, Mapping) else None
        matched = indexed.get(digest) if _sha256(digest) else None
        if not isinstance(raw, Mapping) or set(raw) != _BINDING_FIELDS \
                or matched is None or matched[0] <= previous:
            raise ValueError("rust_cargo_product_witness_inspection_invalid")
        expected = _inspection_binding(matched[1], raw.get("inspection"))
        if dict(raw) != expected:
            raise ValueError("rust_cargo_product_witness_inspection_invalid")
        previous = matched[0]
        result.append(expected)
    return result


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


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


__all__ = [
    "build_rust_cargo_product_witness", "reopen_rust_cargo_product_witness",
    "validate_rust_cargo_product_witness",
]
