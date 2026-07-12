"""Path, hash, and schema helpers for native build closure resolution."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REPARSE_POINT_ATTRIBUTE = 0x400


def sha256_path(path: str | Path) -> str:
    """Hash a file, or a directory as an ordered tree of names and file hashes."""

    candidate = Path(path)
    if _is_link(candidate):
        raise ValueError(f"path must not be a symlink: {candidate}")
    if candidate.is_file():
        return hashlib.sha256(candidate.read_bytes()).hexdigest()
    if not candidate.is_dir():
        raise ValueError(f"path does not exist: {candidate}")

    digest = hashlib.sha256()
    children = [
        child
        for child in candidate.rglob("*")
        if ".git" not in child.relative_to(candidate).parts
    ]
    for child in sorted(children, key=lambda item: item.relative_to(candidate).as_posix()):
        if _is_link(child):
            raise ValueError(f"directory tree must not contain symlinks: {child}")
        relative = child.relative_to(candidate).as_posix().encode("utf-8")
        if child.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif child.is_file():
            digest.update(b"F\0" + relative + b"\0")
            digest.update(hashlib.sha256(child.read_bytes()).digest())
        else:
            raise ValueError(f"directory tree contains an unsupported entry: {child}")
    return digest.hexdigest()


def _checked_repo_root(value: str | Path) -> Path:
    root = Path(value).absolute()
    if _is_link(root) or not root.is_dir():
        raise ValueError("repo_root must be an existing non-symlink directory")
    return root.resolve(strict=True)


def _checked_external_directory(value: str | Path, label: str) -> Path:
    candidate = Path(value).absolute()
    if _is_link(candidate) or not candidate.is_dir():
        raise ValueError(f"{label} must be an existing non-symlink directory")
    return candidate.resolve(strict=True)


def _checked_output_under(base: Path, value: str | Path, label: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        output = candidate
    else:
        cwd_candidate = candidate.absolute()
        try:
            cwd_candidate.relative_to(base)
        except ValueError:
            output = base / candidate
        else:
            output = cwd_candidate
    if not candidate.name or candidate.name in {".", ".."}:
        raise ValueError(f"{label} must name a file")
    parent = output.parent
    try:
        parent_matches = parent.is_dir() and os.path.samefile(parent, base)
    except OSError:
        parent_matches = False
    if not parent_matches:
        raise ValueError(f"{label} must be a direct child of evidence_dir")
    output = base / output.name
    if output.exists() and (_is_link(output) or not output.is_file()):
        raise ValueError(f"{label} must be a regular file when it exists")
    return output


def _verify_path_ref(
    root: Path,
    ref: Mapping[str, Any],
    label: str,
    *,
    expected_kind: str,
) -> tuple[Path, str, str]:
    path_value = ref.get("path")
    sha_value = ref.get("sha256")
    if not isinstance(path_value, str):
        raise ValueError(f"{label}.path must be a repo-relative string")
    if not isinstance(sha_value, str) or SHA256_PATTERN.fullmatch(sha_value) is None:
        raise ValueError(f"{label}.sha256 must be a lowercase SHA-256")
    path = _checked_relative_path(root, path_value, f"{label}.path")
    if expected_kind == "file" and not path.is_file():
        raise ValueError(f"{label}.path must name an existing file")
    if expected_kind == "directory" and not path.is_dir():
        raise ValueError(f"{label}.path must name an existing directory")
    actual_sha = sha256_path(path)
    if actual_sha != sha_value:
        raise ValueError(f"{label}.sha256 does not match {path_value}")
    return path, path_value, sha_value


def _checked_relative_path(root: Path, value: str, label: str) -> Path:
    if not value or "\\" in value or value.startswith("~"):
        raise ValueError(f"{label} must be a canonical repo-relative POSIX path")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts:
        raise ValueError(f"{label} must not be absolute or contain '..'")
    if posix.as_posix() != value:
        raise ValueError(f"{label} must be a canonical repo-relative POSIX path")

    candidate = root
    for part in posix.parts:
        if part == ".":
            continue
        candidate = candidate / part
        if not candidate.exists():
            raise ValueError(f"{label} does not exist: {value}")
        if _is_link(candidate):
            raise ValueError(f"{label} must not traverse a symlink: {value}")
    try:
        candidate.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} escapes repo_root: {value}") from exc
    return candidate


def _symbol_bindings(
    root: Path, value: Any, artifact_hashes: Mapping[str, str]
) -> list[dict[str, Any]]:
    bindings = _mapping_list(value, "manifest.symbol_bindings")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, binding in enumerate(bindings):
        label = f"manifest.symbol_bindings[{index}]"
        source_symbol = binding.get("source_symbol")
        linked_symbol = binding.get("linked_symbol")
        if not isinstance(source_symbol, str) or not source_symbol.strip():
            raise ValueError(f"{label}.source_symbol must be a non-empty string")
        if not isinstance(linked_symbol, str) or not linked_symbol.strip():
            raise ValueError(f"{label}.linked_symbol must be a non-empty string")
        if source_symbol in seen:
            raise ValueError(
                f"manifest.symbol_bindings contains duplicate source_symbol: {source_symbol}"
            )
        artifact = _required_mapping(binding.get("artifact"), f"{label}.artifact")
        _, artifact_path, artifact_sha = _verify_path_ref(
            root, artifact, f"{label}.artifact", expected_kind="file"
        )
        if artifact_hashes.get(artifact_path) != artifact_sha:
            raise ValueError(f"{label}.artifact must reference a declared link artifact")
        seen.add(source_symbol)
        normalized.append(
            {
                "source_symbol": source_symbol,
                "linked_symbol": linked_symbol,
                "artifact": {"path": artifact_path, "sha256": artifact_sha},
            }
        )
    return normalized


def _required_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _build_config(value: Any) -> dict[str, Any]:
    config = _required_mapping(value, "manifest.build_config")
    generator = config.get("generator")
    build_type = config.get("build_type")
    build_target = config.get("build_target")
    for label, item in (
        ("generator", generator),
        ("build_type", build_type),
        ("build_target", build_target),
    ):
        if not isinstance(item, str) or not item:
            raise ValueError(f"manifest.build_config.{label} must be a non-empty string")
    return {
        "generator": generator,
        "build_type": build_type,
        "build_target": build_target,
        "configure_defines": _string_list(
            config.get("configure_defines"),
            "manifest.build_config.configure_defines",
        ),
    }


def _target_abi(value: Any) -> dict[str, Any]:
    target = _required_mapping(value, "manifest.target_abi")
    triple = target.get("triple")
    endianness = target.get("endianness")
    pointer_width = target.get("pointer_width")
    if not isinstance(triple, str) or not triple:
        raise ValueError("manifest.target_abi.triple must be a non-empty string")
    if endianness not in {"little", "big"}:
        raise ValueError("manifest.target_abi.endianness must be little or big")
    if not isinstance(pointer_width, int) or isinstance(pointer_width, bool) or pointer_width <= 0:
        raise ValueError("manifest.target_abi.pointer_width must be a positive integer")
    return {
        "triple": triple,
        "endianness": endianness,
        "pointer_width": pointer_width,
    }


def _string_mapping(value: Any, label: str) -> dict[str, str]:
    mapping = _required_mapping(value, label)
    if not mapping or any(
        not isinstance(key, str)
        or not key
        or not isinstance(item, str)
        or not item
        for key, item in mapping.items()
    ):
        raise ValueError(f"{label} must contain non-empty string keys and values")
    return {key: mapping[key] for key in sorted(mapping)}


def _mapping_list(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must be a list of objects")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    return list(value)


def _repo_relative(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return relative or "."


def _logical_working_directory(root: Path, path: Path) -> str:
    try:
        return _repo_relative(root, path)
    except ValueError:
        return path.as_posix()


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & REPARSE_POINT_ATTRIBUTE)
