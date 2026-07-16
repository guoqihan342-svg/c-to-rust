from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .build_facts import is_absolute_any_platform, resolve_repository_path


_RESERVED_MARKER = "<repo>"
_EMBEDDED_ABSOLUTE = re.compile(r"(?:^|=)(?:/[^/]|[A-Za-z]:[\\/])")


def build_output_index(build_ir: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    targets = build_ir.get("targets")
    if not isinstance(targets, list):
        raise ValueError("project_test_build_ir_targets_invalid")
    for target in targets:
        if not isinstance(target, Mapping) or target.get("kind") != "link":
            continue
        target_id = target.get("target_id")
        outputs = target.get("outputs")
        if not isinstance(target_id, str) or not isinstance(outputs, list):
            raise ValueError("project_test_build_ir_target_invalid")
        for output in outputs:
            if not isinstance(output, Mapping):
                raise ValueError("project_test_build_ir_output_invalid")
            path = output.get("path")
            if not isinstance(path, str) or not path or path in result:
                raise ValueError("project_test_build_ir_output_ambiguous")
            result[path] = {"target_id": target_id, "binding": dict(output)}
    return result


def normalize_command_path(
    value: str, *, repo_root: Path, base: Path,
) -> tuple[str, Path]:
    path = resolve_repository_path(repo_root, value, base=base)
    return path.relative_to(repo_root.resolve()).as_posix(), path


def normalize_argument(
    value: Any, *, repo_root: Path, base: Path,
) -> dict[str, str]:
    return _normalize_value(value, repo_root=repo_root, base=base)


def normalize_environment(
    value: Any, *, repo_root: Path, base: Path,
) -> dict[str, dict[str, str]]:
    if value is None or value == "":
        return {}
    raw: Sequence[Any]
    if isinstance(value, str):
        raw = value.split(";") if value else []
    elif isinstance(value, list):
        raw = value
    else:
        raise ValueError("project_test_environment_invalid")
    result: dict[str, dict[str, str]] = {}
    for item in raw:
        if not isinstance(item, str) or "=" not in item:
            raise ValueError("project_test_environment_invalid")
        name, assigned = item.split("=", 1)
        if (
            not name or not name.replace("_", "a").isalnum()
            or name in result or "\x00" in assigned
            or len(item.encode("utf-8")) > 8192
        ):
            raise ValueError("project_test_environment_invalid")
        result[name] = _normalize_value(
            assigned, repo_root=repo_root, base=base, allow_empty=True,
        )
    return {key: result[key] for key in sorted(result)}


def referenced_repo_paths(value: Mapping[str, Any]) -> tuple[str, ...]:
    paths: set[str] = set()
    arguments = value.get("arguments")
    environment = value.get("environment")
    if not isinstance(arguments, list) or not isinstance(environment, Mapping):
        raise ValueError("project_test_input_binding_invalid")
    for binding in [*arguments, *environment.values()]:
        if not isinstance(binding, Mapping):
            raise ValueError("project_test_input_binding_invalid")
        kind = binding.get("kind")
        if kind in {"repo-path", "repo-path-template"}:
            path = binding.get("path")
            if not isinstance(path, str) or not path:
                raise ValueError("project_test_input_binding_invalid")
            paths.add(path)
        elif kind != "literal":
            raise ValueError("project_test_input_binding_invalid")
    return tuple(sorted(paths))


def expand_input_binding(value: Mapping[str, Any], *, guest_root: str) -> str:
    kind = value.get("kind")
    if kind == "literal" and set(value) == {"kind", "value"}:
        literal = value.get("value")
        if isinstance(literal, str) and _RESERVED_MARKER not in literal:
            return literal
    if kind == "repo-path" and set(value) == {"kind", "path"}:
        return _guest_path(value.get("path"), guest_root)
    if kind == "repo-path-template" and set(value) == {
        "kind", "prefix", "path", "suffix",
    }:
        prefix, suffix = value.get("prefix"), value.get("suffix")
        if isinstance(prefix, str) and isinstance(suffix, str):
            return prefix + _guest_path(value.get("path"), guest_root) + suffix
    raise ValueError("project_test_input_binding_invalid")


def lexical_path(value: str) -> Path:
    return Path(os.path.abspath(value))


def _normalize_value(
    value: Any, *, repo_root: Path, base: Path, allow_empty: bool = False,
) -> dict[str, str]:
    if (
        not isinstance(value, str) or (not value and not allow_empty)
        or len(value.encode("utf-8")) > 4096
        or "\x00" in value or "\r" in value or "\n" in value
        or _RESERVED_MARKER in value
    ):
        raise ValueError("project_test_argument_invalid")
    if is_absolute_any_platform(value):
        return {"kind": "repo-path", "path": _repo_path(value, repo_root, base)}
    existing = (base / value)
    if value and not value.startswith("-") and existing.exists():
        return {"kind": "repo-path", "path": _repo_path(value, repo_root, base)}
    embedded = _embedded_repository_path(value, repo_root, base)
    if embedded is not None:
        prefix, relative, suffix = embedded
        return {
            "kind": "repo-path-template", "prefix": prefix,
            "path": relative, "suffix": suffix,
        }
    if _EMBEDDED_ABSOLUTE.search(value):
        raise ValueError("project_test_external_path_forbidden")
    return {"kind": "literal", "value": value}


def _embedded_repository_path(
    value: str, repo_root: Path, base: Path,
) -> tuple[str, str, str] | None:
    variants = sorted({
        str(repo_root), repo_root.as_posix(),
        str(repo_root.resolve()), repo_root.resolve().as_posix(),
        str(repo_root.resolve()).replace("\\", "/"),
    }, key=len, reverse=True)
    matches = [(value.find(root), root) for root in variants if root and root in value]
    if not matches:
        return None
    index, root = min(matches, key=lambda item: item[0])
    if value.count(root) != 1:
        raise ValueError("project_test_embedded_path_ambiguous")
    candidate = value[index:]
    relative = _repo_path(candidate, repo_root, base)
    return value[:index], relative, ""


def _repo_path(value: str, repo_root: Path, base: Path) -> str:
    relative, path = normalize_command_path(value, repo_root=repo_root, base=base)
    if not path.exists():
        raise ValueError("project_test_input_path_missing")
    return relative


def _guest_path(value: Any, guest_root: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ValueError("project_test_input_binding_invalid")
    parts = Path(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("project_test_input_binding_invalid")
    return guest_root.rstrip("/") + "/" + "/".join(parts)


__all__ = [
    "build_output_index", "expand_input_binding", "lexical_path",
    "normalize_argument", "normalize_command_path", "normalize_environment",
    "referenced_repo_paths",
]
