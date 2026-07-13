from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import cargo_project
from .integration_generation import recover_current_generation
from .integration_validation import MAX_MANIFEST_BYTES, existing_state, read_bounded
from .rust_project_cargo import RUST_PROJECT_IR_FILE
from .rust_project_ir import canonical_rust_project_ir_bytes
from .sandbox_execution_schema import is_sha256


MAX_RUST_PROJECT_IR_BYTES = 2 * 1024 * 1024


def load_managed_project_context(
    project_root: Path, candidate_members: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    generation = recover_current_generation(project_root)
    source = generation or project_root.resolve(strict=True)
    project_input, managed = existing_state(source)
    if not managed or not is_sha256(project_input):
        raise ValueError("managed project generation is unavailable")
    manifest_raw = read_bounded(
        source / cargo_project.LAST_GOOD_MANIFEST, MAX_MANIFEST_BYTES,
    )
    manifest = json.loads(manifest_raw.decode("utf-8"))
    ir_raw = read_bounded(source / RUST_PROJECT_IR_FILE, MAX_RUST_PROJECT_IR_BYTES)
    rust_project_ir = json.loads(ir_raw.decode("utf-8"))
    if (
        not isinstance(manifest, dict)
        or not isinstance(rust_project_ir, dict)
        or canonical_rust_project_ir_bytes(rust_project_ir) != ir_raw
        or manifest.get("rust_project_ir_sha256")
        != rust_project_ir.get("ir_sha256")
        or manifest.get("rust_project_interface_sha256")
        != rust_project_ir.get("interface_sha256")
    ):
        raise ValueError("managed RustProjectIR binding is invalid")
    _require_candidate_cohort(rust_project_ir, candidate_members)
    return {
        "project_input_sha256": project_input,
        "rust_project_ir": rust_project_ir,
        "generation_root": source,
    }


def _require_candidate_cohort(
    rust_project_ir: Mapping[str, Any],
    candidate_members: Sequence[Mapping[str, Any]],
) -> None:
    bindings = rust_project_ir.get("bindings")
    candidates = bindings.get("candidates") if isinstance(bindings, Mapping) else None
    if not isinstance(candidates, list):
        raise ValueError("managed RustProjectIR candidate bindings are missing")
    expected = sorted(
        (
            str(item.get("unit_id")), str(item.get("artifact_id")),
            str(item.get("content_sha256")),
        )
        for item in candidate_members
    )
    actual = sorted(
        (
            str(item.get("unit_id")), str(item.get("artifact_id")),
            str(source.get("sha256")),
        )
        for item in candidates if isinstance(item, Mapping)
        for source in [item.get("source")]
        if isinstance(source, Mapping)
    )
    if actual != expected or len(actual) != len(candidates):
        raise ValueError("managed RustProjectIR candidate cohort drifted")


__all__ = ["load_managed_project_context"]
