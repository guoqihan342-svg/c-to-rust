from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .build_ir import is_sha256
from .gate_evidence import require_content_addressed_reference
from .ledger_security import LedgerError
from .rust_source_pre_cfg_process import (
    MAX_RUST_PARSER_BINARY_BYTES,
    MAX_RUST_PARSER_INPUT_BYTES,
)
from .rust_source_pre_cfg_raw import validate_rust_source_pre_cfg_raw_outputs


RUST_SOURCE_PRE_CFG_RECEIPT_KIND = "rust-source-pre-cfg-witness-receipt"
_CLAIM_BOUNDARY = {
    "phase": "pre-cfg",
    "candidate_only": True,
    "post_cfg": False,
    "section_closure": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
_KEYS = {
    "schema_version", "artifact_kind", "status", "validation_domain",
    "candidate_project_verification", "cargo_topology", "parser_binary",
    "candidates", "claim_boundary", "receipt_sha256",
}
_FACT_KEYS = {
    "module_count", "item_count", "signature_count", "type_count",
    "global_count", "initialization_count", "attribute_count", "macro_count",
    "blocker_count", "cfg_count", "cfg_attr_count",
}


def validate_rust_source_pre_cfg_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _KEYS:
        raise ValueError("rust_source_pre_cfg_receipt_schema_invalid")
    receipt = dict(value)
    domain = _binding(receipt.get("validation_domain"), {
        "reference", "domain_sha256",
    })
    _reference(domain["reference"])
    _sha(domain["domain_sha256"])
    b2a = _binding(receipt.get("candidate_project_verification"), {
        "reference", "verification_context_sha256", "generation_sha256",
    })
    _reference(b2a["reference"])
    _sha(b2a["verification_context_sha256"])
    _sha(b2a["generation_sha256"])
    topology = _binding(receipt.get("cargo_topology"), {
        "reference", "receipt_sha256", "witness_sha256", "status",
    })
    _reference(topology["reference"])
    _sha(topology["receipt_sha256"])
    _sha(topology["witness_sha256"])
    if topology["status"] not in {"ready", "blocked"}:
        raise ValueError("rust_source_pre_cfg_topology_status_invalid")
    parser = _parser(receipt.get("parser_binary"))
    candidates = _candidates(receipt.get("candidates"), parser["sha256"])
    status = "blocked" if (
        topology["status"] == "blocked"
        or any(item["witness_status"] == "blocked" for item in candidates)
    ) else "ready"
    core = {key: receipt[key] for key in receipt if key != "receipt_sha256"}
    if (
        receipt.get("schema_version") != 1
        or receipt.get("artifact_kind") != RUST_SOURCE_PRE_CFG_RECEIPT_KIND
        or receipt.get("status") != status
        or receipt.get("claim_boundary") != _CLAIM_BOUNDARY
        or receipt.get("receipt_sha256") != content_sha256(core)
    ):
        raise ValueError("rust_source_pre_cfg_receipt_identity_invalid")
    return receipt


def rust_source_pre_cfg_claim_boundary() -> dict[str, Any]:
    return dict(_CLAIM_BOUNDARY)


def _candidates(value: Any, parser_sha256: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 20_000:
        raise ValueError("rust_source_pre_cfg_candidates_invalid")
    result = []
    seen: set[str] = set()
    for item in value:
        record = _binding(item, {
            "unit_id", "artifact_id", "source_sha256", "source_size_bytes",
            "process", "raw_outputs", "witness_reference", "witness_status",
            "facts",
        })
        unit_id = _text(record["unit_id"])
        _text(record["artifact_id"])
        source = _sha(record["source_sha256"])
        size = record["source_size_bytes"]
        if (
            unit_id in seen or type(size) is not int
            or not 0 <= size <= MAX_RUST_PARSER_INPUT_BYTES
        ):
            raise ValueError("rust_source_pre_cfg_candidate_identity_invalid")
        seen.add(unit_id)
        _process(record["process"])
        validate_rust_source_pre_cfg_raw_outputs(
            record["raw_outputs"], source_sha256=source,
            parser_binary_sha256=parser_sha256,
        )
        _reference(record["witness_reference"])
        if record["witness_status"] not in {"ready", "blocked"}:
            raise ValueError("rust_source_pre_cfg_candidate_status_invalid")
        _facts(record["facts"])
        result.append(record)
    if result != sorted(result, key=lambda item: (item["unit_id"], item["artifact_id"])):
        raise ValueError("rust_source_pre_cfg_candidates_noncanonical")
    return result


def _parser(value: Any) -> dict[str, Any]:
    parser = _binding(value, {
        "name", "path", "sha256", "size_bytes", "execution_boundary",
        "sandboxed",
    })
    try:
        path = PurePosixPath(checked_relative_path(parser["path"]))
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError("rust_source_pre_cfg_parser_path_invalid") from error
    size = parser["size_bytes"]
    if (
        parser["name"] != "c2r_rust_source_witness"
        or parser["execution_boundary"] != "bounded-stdin-process"
        or parser["sandboxed"] is not False
        or path.name not in {"c2r_rust_source_witness", "c2r_rust_source_witness.exe"}
        or not _is_sha(parser["sha256"])
        or type(size) is not int
        or not 0 < size <= MAX_RUST_PARSER_BINARY_BYTES
    ):
        raise ValueError("rust_source_pre_cfg_parser_binding_invalid")
    return parser


def _process(value: Any) -> None:
    process = _binding(value, {
        "started", "returncode", "timed_out", "output_limit_exceeded",
        "command_sha256",
    })
    if (
        process.get("started") is not True
        or type(process.get("returncode")) is not int
        or process["returncode"] != 0
        or process.get("timed_out") is not False
        or process.get("output_limit_exceeded") is not False
        or not _is_sha(process.get("command_sha256"))
    ):
        raise ValueError("rust_source_pre_cfg_process_invalid")


def _facts(value: Any) -> None:
    facts = _binding(value, _FACT_KEYS)
    if any(type(facts[key]) is not int or facts[key] < 0 for key in _FACT_KEYS):
        raise ValueError("rust_source_pre_cfg_fact_summary_invalid")
    if facts["cfg_count"] + facts["cfg_attr_count"] > facts["attribute_count"]:
        raise ValueError("rust_source_pre_cfg_fact_summary_invalid")


def _reference(value: Any) -> dict[str, Any]:
    try:
        require_content_addressed_reference(value)
    except (KeyError, TypeError, ValueError, LedgerError) as error:
        raise ValueError("rust_source_pre_cfg_reference_invalid") from error
    return dict(value)


def _binding(value: Any, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("rust_source_pre_cfg_binding_invalid")
    return dict(value)


def _text(value: Any) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 1024:
        raise ValueError("rust_source_pre_cfg_text_invalid")
    return value


def _sha(value: Any) -> str:
    if not _is_sha(value):
        raise ValueError("rust_source_pre_cfg_sha256_invalid")
    return value


def _is_sha(value: Any) -> bool:
    return is_sha256(value)


__all__ = [
    "RUST_SOURCE_PRE_CFG_RECEIPT_KIND",
    "rust_source_pre_cfg_claim_boundary",
    "validate_rust_source_pre_cfg_receipt",
]
