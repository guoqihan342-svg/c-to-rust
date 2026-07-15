from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .bounded_artifact_io import write_immutable_artifact
from .build_ir import safe_posix_path


_ROLE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z", re.ASCII)
_SUFFIXES = {"bin", "json"}


def make_cas_reference(
    out_root: str, role: str, data: bytes, *, suffix: str,
) -> dict[str, Any]:
    root = validated_make_output_root(out_root)
    if (
        _ROLE.fullmatch(role) is None or suffix not in _SUFFIXES
        or type(data) is not bytes
    ):
        raise ValueError("make_dry_run_cas_identity_invalid")
    digest = hashlib.sha256(data).hexdigest()
    return {
        "path": f"{root}/cas/{role}/{digest}.{suffix}",
        "sha256": digest,
        "size_bytes": len(data),
    }


def write_make_cas(
    repo_root: Path, out_root: str, role: str, data: bytes, *,
    suffix: str, limit: int,
) -> dict[str, Any]:
    if type(limit) is not int or limit < 0 or len(data) > limit:
        raise ValueError("make_dry_run_cas_size_invalid")
    reference = make_cas_reference(out_root, role, data, suffix=suffix)
    root = repo_root.resolve(strict=True)
    write_immutable_artifact(
        root, PurePosixPath(reference["path"]), data, limit,
    )
    return reference


def validated_make_output_root(value: str) -> str:
    if not safe_posix_path(value):
        raise ValueError("make_dry_run_output_root_invalid")
    path = PurePosixPath(value)
    if len(path.parts) < 2 or path.parts[0] != "target":
        raise ValueError("make_dry_run_output_root_invalid")
    return path.as_posix()


__all__ = [
    "make_cas_reference", "validated_make_output_root", "write_make_cas",
]
