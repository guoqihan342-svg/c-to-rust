from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .build_facts import file_binding, resolve_repository_path
from .build_ir import is_sha256
from .project_test_inventory_make_closure import (
    reject_dynamic_make_line, strip_make_comment,
)
from .project_test_inventory_make_rules import (
    literal_make_rule, rule_mentions_target,
)
from .project_test_inventory_paths import build_output_index


MAX_PREREQUISITES = 256
_BUILTIN_SOURCE_SUFFIXES = (
    ".C", ".F", ".S", ".a", ".c", ".cc", ".ch", ".cpp", ".def",
    ".dvi", ".el", ".elc", ".f", ".h", ".info", ".l", ".lm", ".ln",
    ".m", ".mod", ".o", ".out", ".p", ".r", ".s", ".sh", ".sym",
    ".tex", ".texi", ".texinfo", ".txinfo", ".w", ".web", ".y", ".ym",
)


def bind_direct_leaf_prerequisites(
    root: Path, build: Path, prerequisites: list[str],
    manifests: list[dict[str, Any]], sources: Mapping[str, list[str]],
) -> list[dict[str, Any]]:
    if (
        len(prerequisites) > MAX_PREREQUISITES
        or prerequisites != list(dict.fromkeys(prerequisites))
    ):
        raise ValueError("project_test_make_prerequisite_set_invalid")
    _reject_non_leaf_rules(root, build, prerequisites, manifests, sources)
    _reject_builtin_rule_candidates(root, build, prerequisites)
    result: list[dict[str, Any]] = []
    for name in prerequisites:
        path = resolve_repository_path(root, name, base=build)
        result.append({"name": name, **file_binding(root, path)})
    return result


def valid_prerequisite_bindings(
    value: Any, prerequisites: list[str],
) -> bool:
    if not isinstance(value, list) or len(value) != len(prerequisites):
        return False
    return all(
        isinstance(item, Mapping)
        and set(item) == {"name", "path", "sha256", "size_bytes"}
        and item.get("name") == prerequisites[index]
        and isinstance(item.get("path"), str) and bool(item["path"])
        and is_sha256(item.get("sha256"))
        and isinstance(item.get("size_bytes"), int)
        and not isinstance(item.get("size_bytes"), bool)
        and item["size_bytes"] >= 0
        for index, item in enumerate(value)
    )


def prerequisites_match_build_ir(
    build_ir: Mapping[str, Any], bindings: Any,
) -> bool:
    if not isinstance(bindings, list):
        return False
    try:
        outputs = build_output_index(build_ir)
        for prerequisite in bindings:
            if not isinstance(prerequisite, Mapping):
                return False
            target = outputs.get(prerequisite.get("path"))
            output = target.get("binding") if isinstance(target, Mapping) else None
            if (
                not isinstance(output, Mapping)
                or output.get("materialized") is not True
                or output.get("sha256") != prerequisite.get("sha256")
                or output.get("size_bytes") != prerequisite.get("size_bytes")
            ):
                return False
    except (TypeError, ValueError):
        return False
    return True


def _reject_non_leaf_rules(
    root: Path, build: Path, prerequisites: list[str],
    manifests: list[dict[str, Any]], sources: Mapping[str, list[str]],
) -> None:
    for manifest in manifests:
        for raw in sources[str(manifest["path"])]:
            line = strip_make_comment(raw).strip()
            if not line or raw.startswith("\t"):
                continue
            reject_dynamic_make_line(raw, line)
            left, separator, right = line.partition(":")
            if not separator:
                continue
            left_tokens = left.split()
            if ".PHONY" in left_tokens and any(
                item in right.split() for item in prerequisites
            ):
                raise ValueError("project_test_make_prerequisite_phony")
            if any(
                _implicit_target_matches(pattern, item, root, build)
                for pattern in left_tokens for item in prerequisites
            ):
                raise ValueError("project_test_make_prerequisite_implicit_rule")
            parsed = literal_make_rule(line)
            if parsed is not None and any(
                item in parsed[0] for item in prerequisites
            ):
                raise ValueError("project_test_make_prerequisite_not_direct_leaf")
            if parsed is None and any(
                rule_mentions_target(line, item) for item in prerequisites
            ):
                raise ValueError("project_test_make_prerequisite_rule_unsupported")


def _implicit_target_matches(
    pattern: str, target: str, root: Path, build: Path,
) -> bool:
    if pattern.count("%") == 1:
        prefix, suffix = pattern.split("%")
        return (
            target.startswith(prefix) and target.endswith(suffix)
            and len(target) >= len(prefix) + len(suffix)
        )
    match = re.fullmatch(r"(\.[A-Za-z0-9_+-]+)(\.[A-Za-z0-9_+-]+)", pattern)
    if match:
        return target.endswith(match.group(2))
    return bool(
        re.fullmatch(r"\.[A-Za-z0-9_+-]+", pattern)
        and _source_candidate_exists(root, build, target, pattern)
    )


def _reject_builtin_rule_candidates(
    root: Path, build: Path, prerequisites: list[str],
) -> None:
    for target in prerequisites:
        if any(
            _source_candidate_exists(root, build, target, suffix)
            for suffix in _BUILTIN_SOURCE_SUFFIXES
        ) or _archive_candidate_exists(
            root, resolve_repository_path(root, target, base=build),
        ):
            raise ValueError("project_test_make_prerequisite_builtin_implicit_rule")


def _source_candidate_exists(
    root: Path, build: Path, target: str, suffix: str,
) -> bool:
    target_path = resolve_repository_path(root, target, base=build)
    bases = {target_path, target_path.with_suffix("")}
    for base in bases:
        candidate = Path(str(base) + suffix)
        if candidate == target_path:
            continue
        if candidate.exists() and resolve_repository_path(root, candidate).is_file():
            return True
        if _archive_candidate_exists(root, candidate):
            return True
    return False


def _archive_candidate_exists(root: Path, path: Path) -> bool:
    candidates = (
        Path(str(path) + ",v"), path.parent / "RCS" / (path.name + ",v"),
        path.parent / ("s." + path.name),
        path.parent / "SCCS" / ("s." + path.name),
        )
    for candidate in candidates:
        if candidate.exists() and resolve_repository_path(root, candidate).is_file():
            return True
    return False


__all__ = [
    "MAX_PREREQUISITES", "bind_direct_leaf_prerequisites",
    "prerequisites_match_build_ir", "valid_prerequisite_bindings",
]
