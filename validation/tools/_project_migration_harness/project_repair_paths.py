from __future__ import annotations

from pathlib import Path, PurePosixPath

from .artifacts import checked_relative_path


def require_bound_project_repair_out_root(
    harness_root: Path, out_root: Path, out_root_rel: str,
) -> Path:
    root = harness_root.resolve(strict=True)
    relative = PurePosixPath(checked_relative_path(out_root_rel))
    expected = root.joinpath(*relative.parts).resolve(strict=True)
    actual = out_root.resolve(strict=True)
    if actual != expected:
        raise ValueError("project repair out_root/out_root_rel binding is inconsistent")
    return actual


__all__ = ["require_bound_project_repair_out_root"]
