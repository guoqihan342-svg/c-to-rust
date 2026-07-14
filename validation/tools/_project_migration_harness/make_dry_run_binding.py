from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
import re
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256, safe_posix_path


MAX_TARGETS = 64
MAX_TARGET_BYTES = 256


def fixed_make_argv(makefile: str, targets: Sequence[str]) -> list[str]:
    normalized = validated_targets(targets)
    if not safe_posix_path(makefile):
        raise ValueError("make_dry_run_makefile_ref_invalid")
    return [
        "make", "-B", "-n", "-j1", "--no-print-directory",
        "-f", makefile, "--", *normalized,
    ]


def make_input_sha256(
    makefile_ref: Mapping[str, Any], input_refs: Sequence[Mapping[str, Any]],
    toolchain_ref: Mapping[str, Any],
) -> str:
    return content_sha256({
        "makefile_ref": _artifact_ref(makefile_ref),
        "input_refs": sorted(
            (_artifact_ref(item) for item in input_refs),
            key=lambda item: item["path"],
        ),
        "toolchain_ref": _artifact_ref(toolchain_ref),
    })


def validated_targets(value: Sequence[str]) -> list[str]:
    if (
        isinstance(value, (str, bytes)) or not isinstance(value, Sequence)
        or not 0 < len(value) <= MAX_TARGETS
    ):
        raise ValueError("make_dry_run_targets_invalid")
    result = list(value)
    for target in result:
        path = PurePosixPath(target) if isinstance(target, str) else None
        if (
            not isinstance(target, str) or not target
            or len(target.encode("utf-8")) > MAX_TARGET_BYTES
            or not re.fullmatch(r"[A-Za-z0-9_.+/@%=-]+", target)
            or target.startswith(("-", "~", "/")) or path is None
            or ".." in path.parts or path.as_posix() != target
        ):
            raise ValueError("make_dry_run_target_invalid")
    if len(result) != len(set(result)):
        raise ValueError("make_dry_run_targets_duplicate")
    return result


def _artifact_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("make_dry_run_input_ref_invalid")
    size = value.get("size_bytes")
    if (
        not safe_posix_path(value.get("path"))
        or not is_sha256(value.get("sha256"))
        or isinstance(size, bool) or not isinstance(size, int) or size < 0
    ):
        raise ValueError("make_dry_run_input_ref_invalid")
    return {"path": value["path"], "sha256": value["sha256"], "size_bytes": size}


__all__ = ["fixed_make_argv", "make_input_sha256", "validated_targets"]
