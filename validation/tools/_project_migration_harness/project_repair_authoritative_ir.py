from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .artifacts import checked_relative_path, write_json_artifact
from .build_facts import is_linklike
from .orchestration_facts import MAX_FACT_ARTIFACT_BYTES
from .project_repair_worker_request import read_bound_rust_project_ir
from .rust_project_ir_validation import validate_rust_project_ir


_IR_DIRECTORY = "project-repair/authoritative-ir"


def persist_authoritative_project_ir(
    rust_project_ir: Mapping[str, Any], *, out_root: Path, out_root_rel: str,
) -> dict[str, Any]:
    validate_rust_project_ir(rust_project_ir)
    checked_relative_path(out_root_rel)
    ir_sha256 = _require_sha256(rust_project_ir.get("ir_sha256"))
    reference = write_json_artifact(
        out_root, f"{_IR_DIRECTORY}/{ir_sha256}.json", rust_project_ir,
    )
    return {
        **reference,
        "path": f"{out_root_rel}/{reference['path']}",
        "ir_sha256": ir_sha256,
        "interface_sha256": str(rust_project_ir["interface_sha256"]),
    }


def load_authoritative_project_ir(
    ir_sha256: str, *, harness_root: Path, out_root: Path, out_root_rel: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    digest = _require_sha256(ir_sha256)
    relative = checked_relative_path(f"{_IR_DIRECTORY}/{digest}.json")
    data = _read_regular_artifact(out_root, relative)
    reference = {
        "path": f"{checked_relative_path(out_root_rel)}/{relative}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "ir_sha256": digest,
    }
    value = read_bound_rust_project_ir(harness_root, reference)
    if value["ir_sha256"] != digest:
        raise ValueError("authoritative RustProjectIR identity drifted")
    reference["interface_sha256"] = value["interface_sha256"]
    return value, reference


def _read_regular_artifact(root: Path, relative: str) -> bytes:
    base = root.resolve(strict=True)
    current = base
    for part in PurePosixPath(relative).parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise ValueError("authoritative RustProjectIR path contains a link")
    target = current.resolve(strict=True)
    try:
        target.relative_to(base)
    except ValueError as error:
        raise ValueError("authoritative RustProjectIR escapes out_root") from error
    if target.stat().st_size > MAX_FACT_ARTIFACT_BYTES:
        raise ValueError("authoritative RustProjectIR exceeds the read limit")
    data = target.read_bytes()
    if len(data) > MAX_FACT_ARTIFACT_BYTES:
        raise ValueError("authoritative RustProjectIR exceeds the read limit")
    return data


def _require_sha256(value: Any) -> str:
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("RustProjectIR SHA-256 is invalid")
    return value


__all__ = [
    "load_authoritative_project_ir", "persist_authoritative_project_ir",
]
