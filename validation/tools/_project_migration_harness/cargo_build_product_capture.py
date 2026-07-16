from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from .anchored_artifact_io import (
    DirectoryAnchor, open_directory_anchor, read_anchored_artifact,
)
from .cargo_compiler_artifact_evidence import (
    parse_cargo_compiler_artifact_evidence,
)


MAX_RUST_PRODUCT_BYTES = 256 * 1024 * 1024
MAX_RUST_PRODUCT_TOTAL_BYTES = 512 * 1024 * 1024
MAX_RUST_PRODUCT_COUNT = 512
_GUEST_TARGET = PurePosixPath("/runtime/target")
_PRODUCT_SUFFIXES = {
    "cdylib": (".so",),
    "rlib": (".rlib",),
    "staticlib": (".a",),
}


def capture_cargo_build_products(
    build: Mapping[str, Any], execution_root: Path,
    *, target_anchor: DirectoryAnchor | None = None,
) -> list[dict[str, Any]]:
    source = build.get("_captured_stdout")
    if build.get("status") != "passed" or not isinstance(source, bytes):
        raise ValueError("cargo_build_product_source_unavailable")
    compiler = parse_cargo_compiler_artifact_evidence(source)
    owned_anchor = target_anchor is None
    anchor = target_anchor or open_directory_anchor(
        execution_root.resolve(strict=True) / "target",
    )
    try:
        captured = _capture_products(compiler, anchor)
    finally:
        if owned_anchor:
            anchor.close()
    if not captured:
        raise ValueError("cargo_build_product_missing")
    return sorted(captured, key=_identity)


def _capture_products(
    compiler: Mapping[str, Any], anchor: DirectoryAnchor,
) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str]] = set()
    total = 0
    for artifact in compiler["artifacts"]:
        for product_kind, guest_path in _product_paths(artifact):
            identity = (
                artifact["package_id"], artifact["target"]["name"], product_kind,
            )
            if identity in identities:
                raise ValueError("cargo_build_product_identity_duplicate")
            identities.add(identity)
            data = read_anchored_artifact(
                anchor, _target_relative(guest_path), MAX_RUST_PRODUCT_BYTES,
            )
            if not data:
                raise ValueError("cargo_build_product_empty")
            total += len(data)
            if len(captured) >= MAX_RUST_PRODUCT_COUNT \
                    or total > MAX_RUST_PRODUCT_TOTAL_BYTES:
                raise ValueError("cargo_build_product_capture_limit")
            captured.append({
                "package_id": artifact["package_id"],
                "target": artifact["target"], "product_kind": product_kind,
                "guest_path_sha256": hashlib.sha256(
                    guest_path.encode("utf-8"),
                ).hexdigest(),
                "data": data,
            })
    return captured


def _product_paths(
    artifact: Mapping[str, Any],
) -> list[tuple[str, str]]:
    target = artifact["target"]
    crate_types = set(target["crate_types"])
    result: list[tuple[str, str]] = []
    if "bin" in crate_types:
        executable = artifact.get("executable")
        if not isinstance(executable, str):
            raise ValueError("cargo_build_binary_executable_missing")
        result.append(("bin", executable))
    for crate_type in sorted(crate_types & set(_PRODUCT_SUFFIXES)):
        matches = [
            path for path in artifact["filenames"]
            if path.endswith(_PRODUCT_SUFFIXES[crate_type])
        ]
        if len(matches) != 1:
            raise ValueError("cargo_build_library_product_ambiguous")
        result.append((crate_type, matches[0]))
    if "lib" in crate_types and "rlib" not in crate_types:
        matches = [
            path for path in artifact["filenames"] if path.endswith(".rlib")
        ]
        if len(matches) != 1:
            raise ValueError("cargo_build_library_product_ambiguous")
        result.append(("rlib", matches[0]))
    return result


def _target_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value:
        raise ValueError("cargo_build_product_path_invalid")
    path = PurePosixPath(value)
    try:
        relative = path.relative_to(_GUEST_TARGET)
    except ValueError as error:
        raise ValueError("cargo_build_product_outside_target") from error
    if (
        not path.is_absolute() or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or path.as_posix() != value
    ):
        raise ValueError("cargo_build_product_path_invalid")
    return relative


def _identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(value["package_id"]), str(value["target"]["name"]),
        str(value["product_kind"]),
    )


__all__ = [
    "MAX_RUST_PRODUCT_BYTES", "MAX_RUST_PRODUCT_COUNT",
    "MAX_RUST_PRODUCT_TOTAL_BYTES", "capture_cargo_build_products",
]
