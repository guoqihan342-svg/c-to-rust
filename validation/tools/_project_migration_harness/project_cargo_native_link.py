from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ledger_security import LedgerError
from .project_native_link_settlement import settle_project_native_links
from .project_native_link_settlement_binding import (
    project_native_link_settlement_status,
)
from .project_native_link_state import recover_project_native_link_state


def settle_cargo_native_links(
    *,
    ledger_path: Path,
    out_root: Path,
    context: Mapping[str, Any] | None,
    migration_manifest: Mapping[str, Any] | None,
    execution: Mapping[str, Any],
    checks: Mapping[str, Mapping[str, Any]],
    observations: Mapping[str, Mapping[str, Any]],
    symbol_candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rust_project_ir = _rust_project_ir(context)
    if rust_project_ir is None:
        return project_native_link_settlement_status(
            "blocked", reason_code="native_link_state_unavailable",
        )
    requirements = rust_project_ir.get("native_link_requirements")
    if not isinstance(requirements, list):
        return project_native_link_settlement_status(
            "blocked", reason_code="native_link_state_invalid",
        )
    if not requirements:
        return project_native_link_settlement_status("not-required")
    fallback_context = {"requirement_count": len(requirements)}
    if not isinstance(migration_manifest, Mapping):
        return project_native_link_settlement_status(
            "blocked", context=fallback_context,
            reason_code="native_link_manifest_unavailable",
        )
    try:
        state = recover_project_native_link_state(
            rust_project_ir, migration_manifest, Path(out_root),
        )
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, LedgerError):
        return project_native_link_settlement_status(
            "blocked", context=fallback_context,
            reason_code="native_link_state_unavailable",
        )
    try:
        return settle_project_native_links(
            ledger_path=Path(ledger_path), out_root=Path(out_root),
            native_state=state, rust_project_ir=rust_project_ir,
            execution=execution, checks=checks, observations=observations,
            symbol_candidate=symbol_candidate,
        )
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, LedgerError):
        return project_native_link_settlement_status(
            "blocked", context=state.get("context"),
            candidate=state.get("candidate"),
            reason_code="native_link_settlement_evidence_unavailable",
        )


def _rust_project_ir(
    context: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if not isinstance(context, Mapping):
        return None
    value = context.get("rust_project_ir")
    return value if isinstance(value, Mapping) else None


__all__ = ["settle_cargo_native_links"]
