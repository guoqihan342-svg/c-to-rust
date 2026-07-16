from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from .anchored_artifact_io import DirectoryAnchor, read_anchored_artifact
from .cargo_compiler_artifact_evidence import (
    parse_cargo_compiler_artifact_evidence,
)
from .rustc_dep_info import MAX_RUSTC_DEP_INFO_BYTES, parse_rustc_dep_info


MAX_RUSTC_DEP_INFO_COUNT = 512
MAX_RUSTC_DEP_INFO_TOTAL_BYTES = 64 * 1024 * 1024
_TARGET_ROOT = PurePosixPath("/runtime/target")


def capture_cargo_rustc_dep_info(
    build: Mapping[str, Any], execution_root: Path, *,
    target_anchor: DirectoryAnchor,
) -> list[dict[str, Any]]:
    source = build.get("_captured_stdout")
    if build.get("status") != "passed" or not isinstance(source, bytes):
        raise ValueError("cargo_rustc_dep_info_source_unavailable")
    compiler = parse_cargo_compiler_artifact_evidence(source)
    captured = []
    total = 0
    for artifact in compiler["artifacts"]:
        product = _primary_product(artifact)
        relative = _target_relative(_dep_info_path(product))
        data = read_anchored_artifact(
            target_anchor, relative, MAX_RUSTC_DEP_INFO_BYTES,
        )
        facts = parse_rustc_dep_info(data)
        product_hash = hashlib.sha256(product.encode("utf-8")).hexdigest()
        if facts["product_guest_path_sha256"] != product_hash:
            raise ValueError("cargo_rustc_dep_info_product_binding_drift")
        total += len(data)
        if len(captured) >= MAX_RUSTC_DEP_INFO_COUNT \
                or total > MAX_RUSTC_DEP_INFO_TOTAL_BYTES:
            raise ValueError("cargo_rustc_dep_info_capture_limit")
        captured.append({
            "package_id": artifact["package_id"], "target": artifact["target"],
            "product_guest_path_sha256": product_hash,
            "dep_info_guest_path_sha256": hashlib.sha256(
                (_TARGET_ROOT / relative).as_posix().encode("utf-8"),
            ).hexdigest(),
            "data": data,
        })
    if not captured:
        raise ValueError("cargo_rustc_dep_info_missing")
    identities = {
        (item["package_id"], item["target"]["name"]) for item in captured
    }
    if len(identities) != len(captured):
        raise ValueError("cargo_rustc_dep_info_identity_duplicate")
    return sorted(captured, key=lambda item: (
        str(item["package_id"]), str(item["target"]["name"]),
    ))


def _primary_product(artifact: Mapping[str, Any]) -> str:
    target = artifact["target"]
    crate_types = set(target["crate_types"])
    if "bin" in crate_types:
        executable = artifact.get("executable")
        if not isinstance(executable, str):
            raise ValueError("cargo_rustc_dep_info_binary_missing")
        return executable
    suffixes = (
        ("rlib", ".rlib"), ("lib", ".rlib"),
        ("staticlib", ".a"), ("cdylib", ".so"), ("dylib", ".so"),
    )
    for crate_type, suffix in suffixes:
        if crate_type not in crate_types:
            continue
        matches = [path for path in artifact["filenames"] if path.endswith(suffix)]
        if len(matches) != 1:
            raise ValueError("cargo_rustc_dep_info_product_ambiguous")
        return matches[0]
    raise ValueError("cargo_rustc_dep_info_product_unsupported")


def _dep_info_path(product: str) -> str:
    path = PurePosixPath(product)
    name = path.name
    if name.endswith(".rlib") and path.parent.name == "deps":
        stem = name[:-5]
        if not stem.startswith("lib") or len(stem) <= 3:
            raise ValueError("cargo_rustc_dep_info_rlib_path_invalid")
        return path.with_name(stem[3:] + ".d").as_posix()
    if path.suffix:
        return path.with_suffix(".d").as_posix()
    return path.with_name(name + ".d").as_posix()


def _target_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value:
        raise ValueError("cargo_rustc_dep_info_path_invalid")
    path = PurePosixPath(value)
    try:
        relative = path.relative_to(_TARGET_ROOT)
    except ValueError as error:
        raise ValueError("cargo_rustc_dep_info_outside_target") from error
    if (
        not path.is_absolute() or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or path.as_posix() != value
    ):
        raise ValueError("cargo_rustc_dep_info_path_invalid")
    return relative


__all__ = [
    "MAX_RUSTC_DEP_INFO_COUNT", "MAX_RUSTC_DEP_INFO_TOTAL_BYTES",
    "capture_cargo_rustc_dep_info",
]
