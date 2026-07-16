from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .bounded_artifact_io import (
    BoundedArtifactIOError, read_bounded_artifact, write_immutable_artifact,
)
from .cargo_build_product_capture import MAX_RUST_PRODUCT_BYTES
from .sandbox_execution_schema import is_sha256


_PACKAGE_SUFFIX = re.compile(
    r"(?P<name>[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})@"
    r"(?P<version>[A-Za-z0-9][A-Za-z0-9.+_-]{0,127})\Z",
    re.ASCII,
)
_PRODUCT_KINDS = {"bin", "cdylib", "rlib", "staticlib"}
_PRODUCT_KEYS = {
    "schema_version", "package", "target", "product_kind",
    "guest_path_sha256", "file", "product_sha256",
}
_PACKAGE_KEYS = {"name", "version", "package_id_sha256"}
_TARGET_KEYS = {"name", "kind", "crate_types"}
_FILE_KEYS = {"path", "sha256", "size_bytes"}


def persist_captured_rust_products(
    execution: Mapping[str, Any], *, out_root: Path, required: bool,
) -> dict[str, Any]:
    if type(required) is not bool:
        raise ValueError("Rust product requirement must be a boolean")
    result = dict(execution)
    captured = result.pop("_captured_rust_products", None)
    if not required:
        result["rust_products"] = []
        return result
    try:
        if not isinstance(captured, list) or not captured:
            raise ValueError("captured Rust products are unavailable")
        products = [
            _persist_product(out_root.resolve(strict=True), item)
            for item in captured
        ]
        products = _canonical_products(products)
    except (KeyError, OSError, TypeError, ValueError, BoundedArtifactIOError):
        result["rust_products"] = []
        result["status"] = "blocked"
        diagnostics = result.get("diagnostics")
        result["diagnostics"] = [
            *(diagnostics if isinstance(diagnostics, list) else []),
            {
                "code": "rust_product_evidence_unavailable",
                "stage": "cargo-build-products",
                "message": "Cargo build products could not be persisted",
            },
        ]
        return result
    result["rust_products"] = products
    return result


def read_rust_product(
    ledger_path: Path, product: Mapping[str, Any],
) -> bytes:
    normalized = validate_rust_product_evidence(product)
    database = Path(ledger_path).resolve(strict=True)
    if database.name != "project-migration.sqlite3" \
            or database.parent.name != "state":
        raise ValueError("Rust product requires the fixed ledger path")
    root = database.parent.parent.resolve(strict=True)
    relative = PurePosixPath(normalized["file"]["path"])
    target = root.joinpath(*relative.parts)
    try:
        data = read_bounded_artifact(root, target, MAX_RUST_PRODUCT_BYTES)
    except BoundedArtifactIOError as error:
        raise ValueError("Rust product is not safely readable") from error
    if (
        len(data) != normalized["file"]["size_bytes"]
        or hashlib.sha256(data).hexdigest() != normalized["file"]["sha256"]
    ):
        raise ValueError("Rust product content binding drifted")
    return data


def validate_rust_product_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PRODUCT_KEYS:
        raise ValueError("rust_product_evidence_schema_invalid")
    product = dict(value)
    package = product.get("package")
    target = product.get("target")
    file = product.get("file")
    if (
        product.get("schema_version") != 1
        or not isinstance(package, Mapping) or set(package) != _PACKAGE_KEYS
        or not _text(package.get("name")) or not _text(package.get("version"))
        or not is_sha256(package.get("package_id_sha256"))
        or not isinstance(target, Mapping) or set(target) != _TARGET_KEYS
        or not _text(target.get("name"))
        or not _texts(target.get("kind"))
        or not _texts(target.get("crate_types"))
        or product.get("product_kind") not in _PRODUCT_KINDS
        or not is_sha256(product.get("guest_path_sha256"))
        or not isinstance(file, Mapping) or set(file) != _FILE_KEYS
        or not _file_reference(file)
    ):
        raise ValueError("rust_product_evidence_invalid")
    core = {key: product[key] for key in product if key != "product_sha256"}
    if product.get("product_sha256") != content_sha256(core):
        raise ValueError("rust_product_evidence_sha256_drifted")
    return product


def _persist_product(root: Path, value: Any) -> dict[str, Any]:
    required = {
        "package_id", "target", "product_kind", "guest_path_sha256", "data",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("captured Rust product schema is invalid")
    data = value["data"]
    package_id = value["package_id"]
    target = value["target"]
    match = _PACKAGE_SUFFIX.search(str(package_id))
    if (
        not isinstance(data, bytes) or not data
        or not isinstance(package_id, str) or match is None
        or not isinstance(target, Mapping)
    ):
        raise ValueError("captured Rust product is invalid")
    digest = hashlib.sha256(data).hexdigest()
    relative = PurePosixPath(checked_relative_path(
        f"verification/rust-products/{digest}.bin",
    ))
    write_immutable_artifact(root, relative, data, MAX_RUST_PRODUCT_BYTES)
    core = {
        "schema_version": 1,
        "package": {
            "name": match.group("name"), "version": match.group("version"),
            "package_id_sha256": hashlib.sha256(
                package_id.encode("utf-8"),
            ).hexdigest(),
        },
        "target": {
            "name": target.get("name"),
            "kind": target.get("kind"),
            "crate_types": target.get("crate_types"),
        },
        "product_kind": value["product_kind"],
        "guest_path_sha256": value["guest_path_sha256"],
        "file": {
            "path": relative.as_posix(), "sha256": digest,
            "size_bytes": len(data),
        },
    }
    return validate_rust_product_evidence({
        **core, "product_sha256": content_sha256(core),
    })


def _canonical_products(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(values, key=canonical_json_bytes)
    identities = {
        (item["package"]["name"], item["package"]["version"],
         item["target"]["name"], item["product_kind"])
        for item in ordered
    }
    if not ordered or len(identities) != len(ordered):
        raise ValueError("Rust product identity is ambiguous")
    return ordered


def _file_reference(value: Mapping[str, Any]) -> bool:
    digest = value.get("sha256")
    size = value.get("size_bytes")
    try:
        path = PurePosixPath(checked_relative_path(str(value.get("path"))))
    except ValueError:
        return False
    return (
        is_sha256(digest) and type(size) is int and 0 < size <= MAX_RUST_PRODUCT_BYTES
        and path.parts == ("verification", "rust-products", f"{digest}.bin")
    )


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 256


def _texts(value: Any) -> bool:
    return (
        isinstance(value, list) and bool(value)
        and value == sorted(set(value)) and all(_text(item) for item in value)
    )


__all__ = [
    "persist_captured_rust_products", "read_rust_product",
    "validate_rust_product_evidence",
]
