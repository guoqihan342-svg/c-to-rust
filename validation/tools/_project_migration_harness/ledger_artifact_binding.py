from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ledger_security import LedgerError
from .orchestration_facts import read_artifact_reference


def read_ledger_artifact(
    ledger_path: Path, reference: Mapping[str, Any],
) -> tuple[bytes, Path]:
    if set(reference) not in (
        {"path", "sha256"}, {"path", "sha256", "size_bytes"},
    ):
        raise LedgerError("ledger artifact reference schema is invalid")
    matches: list[tuple[bytes, Path]] = []
    database = ledger_path.resolve()
    bare = {"path": reference.get("path"), "sha256": reference.get("sha256")}
    for candidate in (database.parent, *database.parents):
        try:
            data = read_artifact_reference(candidate, bare)
        except (OSError, ValueError):
            continue
        matches.append((data, candidate.resolve()))
    roots = {root for _data, root in matches}
    if len(roots) != 1 or not matches:
        raise LedgerError("ledger artifact repository root is missing or ambiguous")
    data, root = matches[0]
    size = reference.get("size_bytes", len(data))
    if isinstance(size, bool) or not isinstance(size, int) or size != len(data):
        raise LedgerError("ledger artifact size binding drifted")
    return data, root


def candidate_source_reference(
    ledger_path: Path, candidate: Mapping[str, Any],
) -> dict[str, Any]:
    reference = {
        "path": str(candidate.get("repo_rel_path", "")),
        "sha256": str(candidate.get("content_sha256", "")),
    }
    data, _root = read_ledger_artifact(ledger_path, reference)
    if not data:
        raise LedgerError("candidate source is empty")
    return {**reference, "size_bytes": len(data)}


__all__ = ["candidate_source_reference", "read_ledger_artifact"]
