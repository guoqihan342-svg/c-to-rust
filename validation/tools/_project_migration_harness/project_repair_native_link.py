from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, write_json_artifact
from .ledger_run_contract import load_migration_contract
from .native_link_context import (
    model_native_link_context,
    reopen_native_link_context,
    validate_native_link_context,
)
from .orchestration_facts import read_artifact_reference
from .project_native_link_state import recover_project_native_link_state


def prepare_native_link_repair_context(
    *, ledger: Any, run_id: str, rust_project_ir: Mapping[str, Any],
    out_root: Path, out_root_rel: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with ledger.connect() as connection:
        _contract, migration_manifest = load_migration_contract(
            ledger.path, connection, run_id,
        )
    state = recover_project_native_link_state(
        rust_project_ir, migration_manifest, out_root,
    )
    context = state.get("context")
    if (
        state.get("status") != "candidate-missing"
        or not isinstance(context, Mapping)
        or state.get("candidate") is not None
    ):
        raise ValueError("native link repair does not require model planning")
    validate_native_link_context(context)
    reference = write_json_artifact(
        out_root,
        f"project-repair/native-link-contexts/{context['context_sha256']}.json",
        context,
    )
    return dict(context), {
        **reference,
        "path": f"{out_root_rel}/{reference['path']}",
        "context_sha256": context["context_sha256"],
    }


def read_native_link_repair_context(
    *, harness_root: Path, artifact_root: Path,
    reference: Mapping[str, Any], model_context: Mapping[str, Any],
) -> dict[str, Any]:
    raw = read_artifact_reference(harness_root, reference)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("native link repair context is not UTF-8 JSON") from error
    if (
        not isinstance(value, dict)
        or canonical_json_bytes(value) != raw
        or reference.get("context_sha256") != value.get("context_sha256")
    ):
        raise ValueError("native link repair context binding is invalid")
    validate_native_link_context(value)
    reopen_native_link_context(value, artifact_root)
    if model_native_link_context(value) != dict(model_context):
        raise ValueError("native link repair model context drifted")
    return value


__all__ = [
    "prepare_native_link_repair_context", "read_native_link_repair_context",
]
