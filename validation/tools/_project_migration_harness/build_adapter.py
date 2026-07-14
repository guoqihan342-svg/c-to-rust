from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, TypeAlias

from .build_ir import is_sha256
from .make_build_ir_adapter import (
    MAKE_INPUT_KIND,
    MakeReportSelection,
    discover_make_project,
    materialize_make_build_ir_stage,
)


MAKE_REPORT_INPUT_KIND = MAKE_INPUT_KIND
MAX_BUILD_INPUT_BYTES = 64 * 1024 * 1024
_INPUT_KIND = re.compile(r"[a-z][a-z0-9-]{0,95}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class BuildInputSelection:
    """Adapter-neutral explicit build input with an immutable file binding."""

    kind: str
    path: Path
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, str)
            or _INPUT_KIND.fullmatch(self.kind) is None
            or not isinstance(self.path, Path)
            or not is_sha256(self.sha256)
            or isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or not 0 < self.size_bytes <= MAX_BUILD_INPUT_BYTES
        ):
            raise ValueError("build_input_selection_invalid")

    @property
    def binding(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


BuildInputSelectionLike: TypeAlias = BuildInputSelection | MakeReportSelection


def normalize_build_input_selection(
    selection: BuildInputSelectionLike | None,
) -> BuildInputSelection | None:
    if selection is None:
        return None
    if isinstance(selection, BuildInputSelection):
        return selection
    if isinstance(selection, MakeReportSelection):
        return BuildInputSelection(
            kind=MAKE_REPORT_INPUT_KIND,
            path=selection.path,
            sha256=selection.sha256,
            size_bytes=selection.size_bytes,
        )
    raise ValueError("build_input_selection_invalid")


def discover_selected_project(
    repo_root: str | Path,
    selection: BuildInputSelectionLike,
    max_units: int,
) -> dict[str, Any]:
    checked = _make_selection(selection)
    return discover_make_project(repo_root, checked, max_units)


def materialize_selected_build_ir_stage(
    repo_root: Path,
    output: Path,
    discovery: Mapping[str, Any],
    artifacts: dict[str, dict[str, Any]],
    selection: BuildInputSelectionLike | None,
    profile: str = "development",
) -> dict[str, Any]:
    input_kind = discovery.get("input_kind")
    if input_kind == MAKE_REPORT_INPUT_KIND:
        if selection is None:
            raise ValueError("build_input_selection_missing")
        return materialize_make_build_ir_stage(
            repo_root,
            output,
            discovery,
            artifacts,
            _make_selection(selection),
            profile,
        )
    if selection is not None:
        raise ValueError("build_input_selection_discovery_mismatch")
    from .generated_closure import materialize_build_ir_stage

    return materialize_build_ir_stage(
        repo_root, output, dict(discovery), artifacts, profile,
    )


def _make_selection(selection: BuildInputSelectionLike) -> MakeReportSelection:
    checked = normalize_build_input_selection(selection)
    if checked is None or checked.kind != MAKE_REPORT_INPUT_KIND:
        raise ValueError("build_input_kind_unsupported")
    return MakeReportSelection(
        path=checked.path,
        sha256=checked.sha256,
        size_bytes=checked.size_bytes,
    )


__all__ = [
    "BuildInputSelection",
    "BuildInputSelectionLike",
    "MAKE_REPORT_INPUT_KIND",
    "MAX_BUILD_INPUT_BYTES",
    "discover_selected_project",
    "materialize_selected_build_ir_stage",
    "normalize_build_input_selection",
]
