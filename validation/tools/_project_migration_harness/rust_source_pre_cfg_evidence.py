from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .gate_evidence import (
    read_content_addressed_json,
    write_content_addressed_json,
)
from .ledger_security import LedgerError
from .project_interface_validation_domain_contract import artifact_reference
from .rust_source_pre_cfg_context import reopen_rust_source_pre_cfg_context
from .rust_source_pre_cfg_process import (
    RustSourceProcessResult,
    bind_rust_source_parser_binary,
    run_rust_source_parser,
)
from .rust_source_pre_cfg_raw import (
    read_rust_source_pre_cfg_raw_outputs,
    write_rust_source_pre_cfg_raw_outputs,
)
from .rust_source_pre_cfg_receipt import (
    RUST_SOURCE_PRE_CFG_RECEIPT_KIND,
    rust_source_pre_cfg_claim_boundary,
    validate_rust_source_pre_cfg_receipt,
)
from .rust_source_pre_cfg_schema import parse_rust_source_pre_cfg_witness


RUST_SOURCE_PRE_CFG_SCOPE = "rust-source-pre-cfg-witness-receipt"
RUST_SOURCE_PRE_CFG_DERIVED_SCOPE = "rust-source-pre-cfg-derived"


def materialize_rust_source_pre_cfg_evidence(
    *, ledger_path: Path, out_root: Path,
    validation_domain: Mapping[str, Any],
    cargo_topology_evidence: Mapping[str, Any], repo_root: Path,
    artifact_root: Path, harness_root: Path, quarantine_root: Path,
    tool_root: Path, parser_binary: Path,
    environment: Mapping[str, str] | None = None,
    resolver: Any = None, domain_runner: Any = None,
    parser_runner: Any = None,
) -> dict[str, Any]:
    database = _fixed_ledger_path(ledger_path)
    root = _fixed_out_root(database, out_root)
    receipt = _derive(
        database=database, validation_domain=validation_domain,
        cargo_topology_evidence=cargo_topology_evidence,
        repo_root=repo_root, artifact_root=artifact_root,
        harness_root=harness_root, quarantine_root=quarantine_root,
        tool_root=tool_root, parser_binary=parser_binary,
        environment=environment, resolver=resolver,
        domain_runner=domain_runner, parser_runner=parser_runner,
        out_root=root, stored=None,
    )
    reference = write_content_addressed_json(
        root, RUST_SOURCE_PRE_CFG_SCOPE, receipt,
    )
    return {"receipt": receipt, "reference": reference}


def reopen_rust_source_pre_cfg_evidence(
    ledger_path: Path, reference: Mapping[str, Any], *,
    repo_root: Path, artifact_root: Path, harness_root: Path,
    quarantine_root: Path, tool_root: Path, parser_binary: Path,
    environment: Mapping[str, str] | None = None,
    resolver: Any = None, domain_runner: Any = None,
    parser_runner: Any = None,
) -> dict[str, Any]:
    database = _fixed_ledger_path(ledger_path)
    bound = artifact_reference(reference)
    stored = read_content_addressed_json(
        database, bound["path"], bound["sha256"],
    )
    if len(canonical_json_bytes(stored)) != bound["size_bytes"]:
        raise LedgerError("Rust source witness receipt size drifted")
    receipt = validate_rust_source_pre_cfg_receipt(stored)
    expected = _derive(
        database=database,
        validation_domain=receipt["validation_domain"]["reference"],
        cargo_topology_evidence=receipt["cargo_topology"]["reference"],
        repo_root=repo_root, artifact_root=artifact_root,
        harness_root=harness_root, quarantine_root=quarantine_root,
        tool_root=tool_root, parser_binary=parser_binary,
        environment=environment, resolver=resolver,
        domain_runner=domain_runner, parser_runner=parser_runner,
        out_root=database.parent.parent, stored=receipt,
    )
    if receipt != expected:
        raise LedgerError("Rust source witness receipt drifted")
    return receipt


def _derive(
    *, database: Path, validation_domain: Mapping[str, Any],
    cargo_topology_evidence: Mapping[str, Any], repo_root: Path,
    artifact_root: Path, harness_root: Path, quarantine_root: Path,
    tool_root: Path, parser_binary: Path,
    environment: Mapping[str, str] | None, resolver: Any,
    domain_runner: Any, parser_runner: Any, out_root: Path,
    stored: Mapping[str, Any] | None,
) -> dict[str, Any]:
    context = reopen_rust_source_pre_cfg_context(
        ledger_path=database, validation_domain=validation_domain,
        cargo_topology_evidence=cargo_topology_evidence,
        repo_root=repo_root, artifact_root=artifact_root,
        harness_root=harness_root, quarantine_root=quarantine_root,
        environment=environment, resolver=resolver,
        domain_runner=domain_runner,
    )
    parser = {
        **bind_rust_source_parser_binary(tool_root, parser_binary),
        "execution_boundary": "bounded-stdin-process",
        "sandboxed": False,
    }
    stored_by_unit = _stored_candidates(stored)
    candidates = []
    for source in context["sources"]:
        previous = stored_by_unit.get(source["unit_id"])
        candidates.append(_candidate_entry(
            database=database, out_root=out_root, source=source,
            parser=parser, tool_root=tool_root, parser_binary=parser_binary,
            parser_runner=parser_runner, stored=previous,
        ))
    if bind_rust_source_parser_binary(tool_root, parser_binary) != {
        key: parser[key] for key in ("name", "path", "sha256", "size_bytes")
    }:
        raise LedgerError("Rust source parser binary drifted during execution")
    if stored is not None and set(stored_by_unit) != {
        item["unit_id"] for item in candidates
    }:
        raise LedgerError("Rust source witness candidate set drifted")
    topology = context["topology"]
    core = {
        "schema_version": 1,
        "artifact_kind": RUST_SOURCE_PRE_CFG_RECEIPT_KIND,
        "status": "blocked" if (
            topology["status"] == "blocked"
            or any(item["witness_status"] == "blocked" for item in candidates)
        ) else "ready",
        "validation_domain": {
            "reference": context["domain_reference"],
            "domain_sha256": context["domain"]["domain_sha256"],
        },
        "candidate_project_verification": {
            "reference": context["b2a_reference"],
            "verification_context_sha256": context["b2a"][
                "verification_context_sha256"
            ],
            "generation_sha256": context["b2a"]["materialization"][
                "generation"
            ]["sha256"],
        },
        "cargo_topology": {
            "reference": context["topology_reference"],
            "receipt_sha256": topology["receipt_sha256"],
            "witness_sha256": topology["witness"]["witness_sha256"],
            "status": topology["status"],
        },
        "parser_binary": parser,
        "candidates": candidates,
        "claim_boundary": rust_source_pre_cfg_claim_boundary(),
    }
    return validate_rust_source_pre_cfg_receipt({
        **core, "receipt_sha256": content_sha256(core),
    })


def _candidate_entry(
    *, database: Path, out_root: Path, source: Mapping[str, Any],
    parser: Mapping[str, Any], tool_root: Path, parser_binary: Path,
    parser_runner: Any, stored: Mapping[str, Any] | None,
) -> dict[str, Any]:
    runner = parser_runner or run_rust_source_parser
    result = runner(
        tool_root=tool_root, parser_binary=parser_binary,
        source=source["source"],
    )
    process = _process(result, source["source_sha256"])
    witness = parse_rust_source_pre_cfg_witness(
        result.stdout, source["source"],
    )
    if result.stderr:
        raise LedgerError("Rust source parser wrote unexpected stderr")
    if stored is None:
        raw = write_rust_source_pre_cfg_raw_outputs(
            out_root, source_sha256=source["source_sha256"],
            parser_binary_sha256=parser["sha256"],
            stdout=result.stdout, stderr=result.stderr,
        )
        witness_reference = write_content_addressed_json(
            out_root, RUST_SOURCE_PRE_CFG_DERIVED_SCOPE, witness,
        )
    else:
        raw = stored["raw_outputs"]
        reopened = read_rust_source_pre_cfg_raw_outputs(
            database, raw, source_sha256=source["source_sha256"],
            parser_binary_sha256=parser["sha256"],
        )
        if reopened != {"stdout": result.stdout, "stderr": result.stderr}:
            raise LedgerError("Rust source parser raw output drifted")
        witness_reference = stored["witness_reference"]
        derived = read_content_addressed_json(
            database, witness_reference["path"], witness_reference["sha256"],
        )
        if (
            len(canonical_json_bytes(derived)) != witness_reference["size_bytes"]
            or derived != witness
        ):
            raise LedgerError("Rust source derived witness drifted")
    return {
        "unit_id": source["unit_id"],
        "artifact_id": source["artifact_id"],
        "source_sha256": source["source_sha256"],
        "source_size_bytes": source["source_size_bytes"],
        "process": process,
        "raw_outputs": raw,
        "witness_reference": witness_reference,
        "witness_status": witness["status"],
        "facts": _fact_summary(witness),
    }


def _process(result: Any, source_sha256: str) -> dict[str, Any]:
    expected_command = content_sha256({
        "argv": ["c2r_rust_source_witness"],
        "stdin_sha256": source_sha256,
    })
    if (
        type(result) is not RustSourceProcessResult
        or not result.started or result.returncode != 0 or result.timed_out
        or result.output_limit_exceeded
        or result.command_sha256 != expected_command
    ):
        raise LedgerError("Rust source parser execution failed")
    return {
        "started": True, "returncode": 0, "timed_out": False,
        "output_limit_exceeded": False,
        "command_sha256": result.command_sha256,
    }


def _fact_summary(witness: Mapping[str, Any]) -> dict[str, int]:
    attributes = witness["attributes"]
    return {
        "module_count": len(witness["modules"]),
        "item_count": len(witness["items"]),
        "signature_count": len(witness["signatures"]),
        "type_count": len(witness["types"]),
        "global_count": len(witness["globals"]),
        "initialization_count": len(witness["initialization"]),
        "attribute_count": len(attributes),
        "macro_count": len(witness["macro_invocations"]),
        "blocker_count": len(witness["blockers"]),
        "cfg_count": sum(item["kind"] == "cfg" for item in attributes),
        "cfg_attr_count": sum(item["kind"] == "cfg_attr" for item in attributes),
    }


def _stored_candidates(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return {item["unit_id"]: item for item in value["candidates"]}


def _fixed_ledger_path(value: Path) -> Path:
    database = Path(value).resolve(strict=True)
    if database.name != "project-migration.sqlite3" or database.parent.name != "state":
        raise LedgerError("Rust source witness requires the fixed ledger path")
    return database


def _fixed_out_root(database: Path, value: Path) -> Path:
    root = Path(value).resolve(strict=True)
    if root != database.parent.parent:
        raise LedgerError("Rust source witness output root is not ledger-bound")
    return root


__all__ = [
    "RUST_SOURCE_PRE_CFG_DERIVED_SCOPE", "RUST_SOURCE_PRE_CFG_SCOPE",
    "materialize_rust_source_pre_cfg_evidence",
    "reopen_rust_source_pre_cfg_evidence",
]
