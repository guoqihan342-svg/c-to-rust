from __future__ import annotations

from pathlib import Path
from typing import Any

from .archive_closure import ranlib_output
from .build_facts import compiler_name
from .closure_paths import bind_repository_artifact, path_error_blocker


def bind_ranlib_commands(
    root: Path,
    base: Path,
    target: dict[str, Any],
    commands: list[list[str]],
    *,
    fact_path: str,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    drivers: list[str] = []
    for command in commands:
        value = ranlib_output(command)
        try:
            bound = bind_repository_artifact(
                root, value or "", base=base, kind="file",
            )
        except (OSError, ValueError) as error:
            blockers.append(path_error_blocker(
                error, role="ranlib_target", path=value or "<missing>",
            ))
            continue
        if bound != target.get("output"):
            blockers.append({"kind": "ranlib_target_mismatch", "path": fact_path})
            continue
        drivers.append(compiler_name(command[0]).lower())
    if drivers:
        target["ranlib_drivers"] = sorted(set(drivers))
    return blockers


__all__ = ["bind_ranlib_commands"]
