from __future__ import annotations

from typing import Any

from .boundary import build_c_boundary
from .common import sha256_text
from .constants import FUNCTION_NAME
from .memory_model import build_memory_model


def build_spec(
    *,
    source: dict[str, Any],
    c_source: str,
    contract: dict[str, Any],
    outputs: list[str],
    target_id: str,
    slice_id: str,
    fixture_path: str,
) -> dict[str, Any]:
    source_file = source["file"]
    source_hash = source["file_sha256"]
    evidence_prefix = f"validation/evidence/{target_id}/auto-translation/{slice_id}"
    return {
        "schema_version": 1,
        "target_id": target_id,
        "slice_id": slice_id,
        "level": "L3",
        "status": "draft",
        "function_name": FUNCTION_NAME,
        "l1_evidence": {
            "path": f"validation/evidence/{target_id}/l1-native-build.json",
            "status": "required",
            "accepted": False,
        },
        "c_source": c_source,
        "translation_carrier": translation_carrier(source, c_source),
        "source_commit": source["source_commit"],
        "fixture_hash": "pending-generation",
        "source_root": source["source_root"],
        "source_file": source_file,
        "source_file_hashes": {source_file: source_hash},
        "source": source_identity(source),
        "c_boundary": build_c_boundary(source_file, source_hash),
        "build_profile": build_profile(target_id, slice_id),
        "fixture_contract": fixture_contract(
            target_id, slice_id, fixture_path, outputs, evidence_prefix
        ),
        "replay_contract": contract,
        "rust_boundary": rust_boundary(evidence_prefix, slice_id),
        "memory_model": build_memory_model(),
        "claim_boundary": {
            "accepted_metadata_differences": [],
            "non_goals": [
                "No real get_next_kv_addr semantics.",
                "No whole fdb_kv_iterate migration claim.",
                "No alias root independent from itr.",
                "No project-name-based translation selection.",
            ],
            "must_not_claim": [
                "whole-project migration",
                "real external-callee equivalence",
                "kv as a third root",
            ],
        },
        "cache_invalidation_keys": [
            "source.source_commit",
            "source.source_file_hashes",
            "source_root",
            "source_file",
            "source_file_hashes",
            "translation_carrier",
            "fixture_contract.hash",
            "replay_contract",
            "memory_model.alias_contract",
            "translator_version",
        ],
    }


def translation_carrier(source: dict[str, Any], c_source: str) -> dict[str, Any]:
    return {
        "kind": "exact_source_fragment_wrapper",
        "carrier_function": FUNCTION_NAME,
        "carrier_source_sha256": sha256_text(c_source),
        "embedding_mode": "verbatim_once",
        "frontend_contract": "live_clang_slice_source",
        "source_text_normalization": "utf8_universal_newlines",
        "source_file_hash_mode": "raw_bytes",
        "artifact_source_hash_mode": "lf_stable_text",
        "real_source": {
            "file": source["file"],
            "containing_function": source["containing_function"],
            "fragment": source["fragment"],
        },
        "claim_boundary": {
            "scope": "source_fragment_only",
            "whole_function_semantics_verified": False,
            "external_callee_semantics_verified": False,
            "excluded_semantics": [
                "the real get_next_kv_addr implementation and side effects",
                "the enclosing fdb_kv_iterate loops and statements outside lines 1868-1874",
                "real FlashDB record layout, ABI, storage, and sector lifecycle",
            ],
        },
    }


def source_identity(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_root": source["source_root"],
        "source_commit": source["source_commit"],
        "repo_commit": source["source_commit"],
        "source_file_hashes": {source["file"]: source["file_sha256"]},
        "source_repository": source["source_repository"],
        "source_branch": source["source_branch"],
    }


def build_profile(target_id: str, slice_id: str) -> dict[str, Any]:
    return {
        "profile_id": f"{target_id}-{slice_id}-carrier",
        "compiler_command_source": "translation-carrier self-contained C plus tests/Makefile ABI",
        "include_paths": [],
        "oracle_harness_includes": [],
        "defines": [],
        "clang_available": True,
        "target": {
            "triple_or_abi": "x86_64-unknown-linux-gnu",
            "endianness": "little",
            "int_width": 32,
            "char_width": 8,
            "plain_char_signed": True,
            "short_width": 16,
            "long_width": 64,
            "long_long_width": 64,
            "pointer_width": 64,
        },
        "target_triple": "x86_64-unknown-linux-gnu",
        "abi": "x86_64-unknown-linux-gnu",
        "preprocessing_mode": "manual_flags",
        "tool_versions": {
            "generate_zero_start_call_continue_slice": "1",
            "translation_carrier_validator": "1",
        },
        "clang_type_extraction": {
            "available": True,
            "mode": "live_clang_slice_source",
            "diagnostics": [
                "The carrier is lowered from embedded c_source; no project-name translation selector or offline AST fixture is accepted."
            ],
        },
    }


def fixture_contract(
    target_id: str,
    slice_id: str,
    fixture_path: str,
    outputs: list[str],
    evidence_prefix: str,
) -> dict[str, Any]:
    return {
        "fixture_id": f"{slice_id}-fixture",
        "path": fixture_path,
        "hash": "pending-generation",
        "cases": [],
        "observable_outputs": outputs,
        "behavior_fields": outputs,
        "c_oracle": f"validation/evidence/{target_id}/l3-{slice_id}-c-oracle.json",
        "rust_report": f"validation/evidence/{target_id}/l3-{slice_id}-rust-report.json",
        "diff": f"validation/evidence/{target_id}/l3-{slice_id}-diff.json",
        "negative_diff": f"validation/evidence/{target_id}/l3-{slice_id}-negative-diff.json",
        "unsafe_scan": f"{evidence_prefix}/l3-{slice_id}-unsafe-scan.json",
        "unsafe_ledger": f"{evidence_prefix}/l3-{slice_id}-unsafe-ledger.json",
    }


def rust_boundary(evidence_prefix: str, slice_id: str) -> dict[str, Any]:
    return {
        "crate": "validation/l2_slices",
        "module": f"{evidence_prefix}/l3-{slice_id}-rust-draft.rs",
        "public_api": [
            {"name": FUNCTION_NAME, "visibility": "public", "boundary_kind": "safe_wrapper"}
        ],
        "raw_pointer_policy": "internal_only",
        "unsafe_policy": {"max_first_party_non_test_ratio": 0.0, "ledger_required": True},
    }
