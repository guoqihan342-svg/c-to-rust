from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .build_facts import resolve_repository_path
from .make_dry_run_binding import (
    normalize_repository_path, validated_targets, validated_working_directory,
)
from .make_dry_run_cas import validated_make_output_root, write_make_cas
from .make_dry_run_contract import MAX_STDERR_BYTES
from .make_dry_run_parser import MAX_STDOUT_BYTES


def validate_make_collection_inputs(
    repo_root: str | Path, working_directory: str, makefile: str,
    targets: Sequence[str], out_root: str, timeout_seconds: int,
) -> tuple[Path, str, str, list[str], str]:
    root = Path(repo_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("make_collection_repository_invalid")
    workdir = validated_working_directory(working_directory)
    workdir_path = resolve_repository_path(
        root, Path(*PurePosixPath(workdir).parts),
    )
    if not workdir_path.is_dir():
        raise ValueError("make_collection_working_directory_invalid")
    makefile_path = normalize_repository_path(makefile, workdir)
    resolved_makefile = resolve_repository_path(
        root, Path(*PurePosixPath(makefile_path).parts),
    )
    if not resolved_makefile.is_file():
        raise ValueError("make_collection_makefile_invalid")
    output = validated_make_output_root(out_root)
    if _inside(output, workdir) or _inside(output, makefile_path):
        raise ValueError("make_collection_output_overlaps_inputs")
    selected_targets = validated_targets(targets)
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 3_600:
        raise ValueError("make_collection_timeout_invalid")
    return root, workdir, makefile_path, selected_targets, output


def persist_make_static(
    root: Path, output: str, **values: tuple[bytes, Mapping[str, Any], int],
) -> dict[str, Any]:
    result = {}
    for key, (data, expected, limit) in values.items():
        role = key.replace("_", "-")
        actual = write_make_cas(
            root, output, role, data, suffix="json", limit=limit,
        )
        if actual != dict(expected):
            raise ValueError("make_collection_cas_reference_drift")
        result[key] = actual
    return result


def persist_make_raw_outputs(
    root: Path, output: str, outcome: Any,
) -> dict[str, Any]:
    result = {}
    for name, limit in (
        ("stdout", MAX_STDOUT_BYTES), ("stderr", MAX_STDERR_BYTES),
    ):
        data = getattr(outcome, name, None)
        if data is None:
            continue
        if type(data) is not bytes:
            raise ValueError("make_collection_raw_output_invalid")
        result[f"raw_{name}"] = write_make_cas(
            root, output, f"raw-{name}", data, suffix="bin", limit=limit,
        )
    return result


def make_command_input_refs(
    commands: list[Mapping[str, Any]], files: Mapping[str, Mapping[str, Any]],
    output_root: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_paths = {
        path for command in commands
        for path in [*command["inputs"], *command["outputs"]]
    }
    if any(_inside(output_root, path) for path in all_paths):
        raise ValueError("make_collection_command_overlaps_output_root")
    produced = {path for command in commands for path in command["outputs"]}
    source_paths = sorted({
        path for command in commands if command["kind"] == "compile"
        for path in command["inputs"]
    })
    input_paths = sorted({
        path for command in commands for path in command["inputs"]
        if path not in produced
    })
    try:
        sources = [dict(files[path]) for path in source_paths]
        inputs = [dict(files[path]) for path in input_paths]
    except KeyError as error:
        raise ValueError("make_collection_unbound_command_input") from error
    if not sources or not inputs or not set(source_paths).issubset(input_paths):
        raise ValueError("make_collection_input_closure_invalid")
    return sources, inputs


def _inside(root: str, value: str) -> bool:
    root_parts = PurePosixPath(root).parts
    value_parts = () if value == "." else PurePosixPath(value).parts
    return tuple(value_parts[:len(root_parts)]) == root_parts


__all__ = [
    "make_command_input_refs", "persist_make_raw_outputs",
    "persist_make_static", "validate_make_collection_inputs",
]
