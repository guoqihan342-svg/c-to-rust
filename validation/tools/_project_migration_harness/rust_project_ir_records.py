from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .rust_ffi_facts import NoFfiBoundaryError, derive_ffi_boundary_facts
from .rust_project_ir_source_facts import project_bound_public_items


def project_evidence(
    builds: Sequence[str], unit_id: str, candidate_sha: str,
) -> dict[str, Any]:
    return {
        "build_ir_sha256s": sorted(builds),
        "dag_unit_ids": [unit_id],
        "candidate_sha256s": [candidate_sha],
    }


def public_records(
    module_id: str, unit_id: str, candidate_sha: str,
    build_digests: Sequence[str], symbols: Sequence[str],
    source_facts: Mapping[str, Any],
) -> list[dict[str, Any]]:
    evidence = project_evidence(build_digests, unit_id, candidate_sha)
    projected = {
        item["symbol"]: item
        for item in project_bound_public_items(symbols, source_facts)
    }
    return [{
        "declaration_id": "api-" + content_sha256({
            "module_id": module_id, "symbol": symbol,
        })[:24],
        "module_id": module_id, "symbol": symbol,
        "kind": projected[symbol]["kind"],
        "signature": projected[symbol]["signature"],
        "visibility": "public", "evidence": evidence,
    } for symbol in symbols]


def ffi_records(
    module_id: str, unit_id: str, candidate_sha: str,
    build_digests: Sequence[str], source: str,
) -> list[dict[str, Any]]:
    evidence = project_evidence(build_digests, unit_id, candidate_sha)
    try:
        facts = derive_ffi_boundary_facts(source, candidate_sha)
    except NoFfiBoundaryError:
        return []
    return [{
        "declaration_id": "ffi-" + content_sha256({
            "module_id": module_id, **fact,
        })[:24],
        "module_id": module_id, **fact, "evidence": evidence,
    } for fact in facts]


def unsafe_records(
    module_id: str, unit_id: str, candidate_sha: str,
    build_digests: Sequence[str], count: int, *, max_count: int,
    target_scoped_identity: bool = False,
) -> list[dict[str, Any]]:
    if count > max_count:
        raise ValueError("candidate_unsafe_obligations_unbounded")
    evidence = project_evidence(build_digests, unit_id, candidate_sha)
    identity = (
        content_sha256({"module_id": module_id, "candidate_sha256": candidate_sha})[:16]
        if target_scoped_identity else candidate_sha[:16]
    )
    return [{
        "obligation_id": f"unsafe-{identity}-{index:04d}",
        "module_id": module_id, "kind": "host-derived-unsafe-token",
        "reason_code": "requires-project-safety-verification",
        "source_span": None, "evidence": evidence,
    } for index in range(count)]


__all__ = [
    "ffi_records", "project_evidence", "public_records", "unsafe_records",
]
