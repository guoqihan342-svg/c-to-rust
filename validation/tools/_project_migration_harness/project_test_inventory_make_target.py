from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .build_facts import resolve_repository_path
from .project_test_inventory_make_closure import (
    MAX_MAKEFILE_BYTES, MAX_MANIFESTS, MAX_TOTAL_BYTES,
    load_static_make_closure, reject_dynamic_make_line, strip_make_comment,
)
from .project_test_inventory_make_prerequisites import (
    bind_direct_leaf_prerequisites, valid_prerequisite_bindings,
)
from .project_test_inventory_make_rules import (
    literal_make_rule, rule_mentions_target,
)
from .project_test_target_proposal import (
    valid_make_target,
    validate_bound_project_test_target_proposal,
)


STATIC_TARGET_KIND = "ai-static-make-target-v1"
MAX_RECIPES = 256
MAX_RECIPE_BYTES = 64 * 1024


def select_static_make_target(
    repo_root: Path, build_directory: Path, proposal_value: Any,
) -> dict[str, Any]:
    try:
        proposal = validate_bound_project_test_target_proposal(proposal_value)
        target = str(proposal["proposal"]["target"])
        root = Path(repo_root).resolve(strict=True)
        build = resolve_repository_path(root, build_directory)
        if not root.is_dir() or not build.is_dir():
            raise ValueError("invalid Make roots")
        manifests, sources = load_static_make_closure(root, build)
        candidate = _extract_candidate(
            root, build, target, manifests, sources,
        )
    except UnicodeError:
        return _blocked("project_test_makefile_encoding_invalid")
    except (OSError, TypeError, ValueError) as error:
        code = str(error)
        if code.startswith("project_test_make_"):
            return _blocked(code)
        return _blocked("project_test_make_static_binding_invalid")
    core = {
        "schema_version": 2,
        "kind": STATIC_TARGET_KIND,
        "target": target,
        "proposal": proposal,
        "entry_makefile": manifests[0]["path"],
        "manifests": manifests,
        "manifest_set_sha256": content_sha256(manifests),
        "candidate": candidate,
        "candidate_sha256": content_sha256(candidate),
        "safety_policy": "static-direct-leaf-recipe-v1",
    }
    return {"status": "selected", "target_binding": core}


def validate_static_make_target_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "kind", "target", "proposal", "entry_makefile",
        "manifests", "manifest_set_sha256", "candidate",
        "candidate_sha256", "safety_policy",
    }:
        raise ValueError("project_test_make_static_binding_invalid")
    proposal = validate_bound_project_test_target_proposal(value.get("proposal"))
    manifests, candidate = value.get("manifests"), value.get("candidate")
    if (
        value.get("schema_version") != 2
        or value.get("kind") != STATIC_TARGET_KIND
        or value.get("target") != proposal["proposal"]["target"]
        or value.get("safety_policy") != "static-direct-leaf-recipe-v1"
        or not isinstance(manifests, list) or not manifests
        or len(manifests) > MAX_MANIFESTS
        or not all(_valid_manifest(item) for item in manifests)
        or len({item["path"] for item in manifests}) != len(manifests)
        or value.get("entry_makefile") != manifests[0]["path"]
        or sum(item["size_bytes"] for item in manifests) > MAX_TOTAL_BYTES
        or value.get("manifest_set_sha256") != content_sha256(manifests)
        or not _valid_candidate(candidate, str(value.get("target")))
        or value.get("candidate_sha256") != content_sha256(candidate)
    ):
        raise ValueError("project_test_make_static_binding_invalid")
    return dict(value)


def verify_static_make_target_binding(
    repo_root: Path, build_directory: Path, value: Any,
) -> bool:
    try:
        current = validate_static_make_target_binding(value)
    except ValueError:
        return False
    expected = select_static_make_target(
        repo_root, build_directory, current["proposal"],
    )
    return (
        expected.get("status") == "selected"
        and expected.get("target_binding") == current
    )


def static_target_commands(value: Any) -> list[str]:
    binding = validate_static_make_target_binding(value)
    return [str(item["command"]) for item in binding["candidate"]["recipes"]]


def _extract_candidate(
    root: Path, build: Path, target: str, manifests: list[dict[str, Any]],
    sources: Mapping[str, list[str]],
) -> dict[str, Any]:
    declarations: list[dict[str, Any]] = []
    recipes: list[dict[str, Any]] = []
    for manifest in manifests:
        path = str(manifest["path"])
        lines = sources[path]
        for index, raw in enumerate(lines):
            line = strip_make_comment(raw).strip()
            if not line or raw.startswith("\t"):
                continue
            reject_dynamic_make_line(raw, line)
            parsed = literal_make_rule(line)
            if parsed is None:
                if rule_mentions_target(line, target):
                    raise ValueError(
                        "project_test_make_proposed_target_rule_unsupported"
                    )
                continue
            if target not in parsed[0]:
                continue
            declarations.append({
                "path": path, "line": index + 1,
                "rule_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            })
            prerequisites = parsed[1]
            offset = index + 1
            while offset < len(lines) and lines[offset].startswith("\t"):
                command = _literal_recipe(lines[offset])
                if command is not None:
                    recipes.append({
                        "path": path, "line": offset + 1, "command": command,
                        "recipe_sha256": hashlib.sha256(
                            lines[offset].encode("utf-8"),
                        ).hexdigest(),
                    })
                offset += 1
    if len(declarations) != 1:
        raise ValueError("project_test_make_proposed_target_ambiguous")
    if not recipes:
        raise ValueError("project_test_make_proposed_target_has_no_direct_recipe")
    if len(recipes) > MAX_RECIPES:
        raise ValueError("project_test_make_recipe_limit_exceeded")
    prerequisite_bindings = bind_direct_leaf_prerequisites(
        root, build, prerequisites, manifests, sources,
    )
    candidate = {
        "target": target,
        "declaration": declarations[0],
        "prerequisites": prerequisites,
        "prerequisite_bindings": prerequisite_bindings,
        "recipes": recipes,
    }
    candidate["candidate_id"] = "make-target-" + content_sha256(candidate)[:24]
    return candidate


def _literal_recipe(raw: str) -> str | None:
    value = raw[1:].lstrip()
    prefixes = value[:len(value) - len(value.lstrip("@+-"))]
    if "+" in prefixes or "-" in prefixes:
        raise ValueError("project_test_make_recipe_prefix_unsupported")
    value = value[len(prefixes):].strip()
    if not value or value.startswith("#"):
        return None
    if (
        "$" in value or "\\" in value
        or len(value.encode("utf-8")) > MAX_RECIPE_BYTES
    ):
        raise ValueError("project_test_make_recipe_dynamic_unsupported")
    return value


def _valid_manifest(value: Any) -> bool:
    size = value.get("size_bytes") if isinstance(value, Mapping) else None
    return (
        isinstance(value, Mapping)
        and set(value) == {"path", "sha256", "size_bytes"}
        and isinstance(value.get("path"), str) and bool(value["path"])
        and isinstance(value.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", str(value["sha256"])) is not None
        and isinstance(size, int) and not isinstance(size, bool)
        and 0 <= size <= MAX_MAKEFILE_BYTES
    )


def _valid_candidate(value: Any, target: str) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "target", "declaration", "prerequisites", "prerequisite_bindings",
        "recipes", "candidate_id",
    }:
        return False
    declaration, prerequisites = value.get("declaration"), value.get("prerequisites")
    recipes = value.get("recipes")
    core = {key: item for key, item in value.items() if key != "candidate_id"}
    return (
        value.get("target") == target
        and _valid_source_record(declaration, "rule_sha256")
        and isinstance(prerequisites, list)
        and len(prerequisites) <= 256
        and all(valid_make_target(item) for item in prerequisites)
        and prerequisites == list(dict.fromkeys(prerequisites))
        and valid_prerequisite_bindings(
            value.get("prerequisite_bindings"), prerequisites,
        )
        and isinstance(recipes, list) and 0 < len(recipes) <= MAX_RECIPES
        and all(
            _valid_source_record(item, "recipe_sha256")
            and isinstance(item.get("command"), str) and bool(item["command"])
            and len(item["command"].encode("utf-8")) <= MAX_RECIPE_BYTES
            for item in recipes
        )
        and value.get("candidate_id")
        == "make-target-" + content_sha256(core)[:24]
    )


def _valid_source_record(value: Any, hash_key: str) -> bool:
    required = {"path", "line", hash_key}
    if hash_key == "recipe_sha256":
        required.add("command")
    return (
        isinstance(value, Mapping) and set(value) == required
        and isinstance(value.get("path"), str) and bool(value["path"])
        and isinstance(value.get("line"), int) and not isinstance(value.get("line"), bool)
        and value["line"] >= 1 and isinstance(value.get(hash_key), str)
        and re.fullmatch(r"[0-9a-f]{64}", str(value[hash_key])) is not None
    )


def _blocked(code: str) -> dict[str, Any]:
    return {"status": "blocked", "blocker": {"code": code}}


__all__ = [
    "STATIC_TARGET_KIND", "select_static_make_target",
    "static_target_commands", "validate_static_make_target_binding",
    "verify_static_make_target_binding",
]
