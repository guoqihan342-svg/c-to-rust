from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .build_facts import resolve_repository_path
from .project_test_inventory_make_records import (
    blocked_inventory, derive_make_command_inventory,
)
from .project_test_inventory_make_prerequisites import (
    prerequisites_match_build_ir,
)
from .project_test_inventory_make_target import (
    select_static_make_target, static_target_commands,
    validate_static_make_target_binding, verify_static_make_target_binding,
)


MAKE_STATIC_ADAPTER = "make-static-direct-v1"
_OBSERVATION_KEYS = {
    "schema_version", "artifact_kind", "target_binding", "build_directory",
    "commands", "commands_sha256", "subprocess_executed", "semantic_gate",
    "observation_sha256",
}


def collect_static_make_test_recipes(
    repo_root: Path, build_directory: Path, *,
    target_proposal: Mapping[str, Any] | None = None,
    expected_target_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        if (target_proposal is None) == (expected_target_binding is None):
            raise ValueError("static Make target authority is ambiguous")
        root = Path(repo_root).resolve(strict=True)
        build = resolve_repository_path(root, build_directory)
        if not root.is_dir() or not build.is_dir():
            raise ValueError("static Make roots are invalid")
        if expected_target_binding is not None:
            binding = validate_static_make_target_binding(expected_target_binding)
            proposal = binding["proposal"]
        else:
            proposal = target_proposal
            binding = None
        selected = select_static_make_target(root, build, proposal)
        if selected.get("status") != "selected":
            return selected
        current = selected["target_binding"]
        if binding is not None and current != binding:
            return _blocked("project_test_make_static_binding_drifted")
        commands = static_target_commands(current)
    except (OSError, TypeError, ValueError):
        return _blocked("project_test_make_static_input_invalid")
    observation = {
        "schema_version": 1,
        "artifact_kind": "make-static-direct-v1-observation",
        "target_binding": current,
        "build_directory": build.relative_to(root).as_posix() or ".",
        "commands": commands,
        "commands_sha256": content_sha256(commands),
        "subprocess_executed": False,
        "semantic_gate": False,
    }
    observation["observation_sha256"] = content_sha256(observation)
    return {"status": "collected", "observation": observation}


def inventory_from_static_make_observation(
    repo_root: Path, build_ir: Mapping[str, Any], observation: Mapping[str, Any],
    *, source_observation: Mapping[str, Any],
) -> dict[str, Any]:
    if not _valid_observation(observation):
        return blocked_inventory("project_test_make_static_schema_invalid")
    try:
        root = Path(repo_root).resolve(strict=True)
        build = resolve_repository_path(root, str(observation["build_directory"]))
        binding = observation["target_binding"]
        if (
            not root.is_dir() or not build.is_dir()
            or not verify_static_make_target_binding(root, build, binding)
            or static_target_commands(binding) != observation["commands"]
            or not prerequisites_match_build_ir(
                build_ir, binding["candidate"]["prerequisite_bindings"],
            )
        ):
            raise ValueError("static Make binding changed")
    except (KeyError, OSError, TypeError, ValueError):
        return blocked_inventory("project_test_make_static_binding_invalid")
    return derive_make_command_inventory(
        root, build, build_ir, observation["commands"],
        source_observation=source_observation, adapter=MAKE_STATIC_ADAPTER,
    )


def _valid_observation(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != _OBSERVATION_KEYS:
        return False
    commands = value.get("commands")
    try:
        binding = validate_static_make_target_binding(value.get("target_binding"))
    except ValueError:
        return False
    return (
        value.get("schema_version") == 1
        and value.get("artifact_kind") == "make-static-direct-v1-observation"
        and isinstance(value.get("build_directory"), str)
        and isinstance(commands, list) and commands
        and all(isinstance(item, str) for item in commands)
        and commands == static_target_commands(binding)
        and value.get("commands_sha256") == content_sha256(commands)
        and value.get("subprocess_executed") is False
        and value.get("semantic_gate") is False
        and value.get("observation_sha256") == content_sha256({
            key: item for key, item in value.items()
            if key != "observation_sha256"
        })
    )


def _blocked(code: str) -> dict[str, Any]:
    return {"status": "blocked", "blocker": {"code": code}}


__all__ = [
    "MAKE_STATIC_ADAPTER", "collect_static_make_test_recipes",
    "inventory_from_static_make_observation",
]
