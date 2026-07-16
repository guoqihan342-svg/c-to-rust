from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .gate_evidence import require_content_addressed_reference
from .ledger_security import LedgerError
from .project_rust_cargo_topology_scope import PROJECT_RUST_CARGO_TOPOLOGY_SCOPE


def fixed_topology_paths(ledger_path: Path, out_root: Path) -> Path:
    database = Path(ledger_path).resolve(strict=True)
    root = Path(out_root).resolve(strict=True)
    if (
        database.name != "project-migration.sqlite3"
        or database.parent.name != "state"
        or root != database.parent.parent
    ):
        raise LedgerError("project Rust Cargo topology paths are not ledger-bound")
    return database


def topology_reference(value: Any) -> dict[str, Any]:
    try:
        require_content_addressed_reference(value)
    except (KeyError, TypeError, ValueError, LedgerError) as error:
        raise ValueError("project_rust_cargo_topology_reference_invalid") from error
    path = PurePosixPath(str(value["path"]))
    if path.parts != (
        "verification", PROJECT_RUST_CARGO_TOPOLOGY_SCOPE,
        f"{value['sha256']}.json",
    ):
        raise ValueError("project_rust_cargo_topology_reference_invalid")
    return dict(value)


__all__ = ["fixed_topology_paths", "topology_reference"]
