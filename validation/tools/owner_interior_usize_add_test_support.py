from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


FIELDS = ["accepted", "updated_total"]
REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("owner_interior_usize_auto_migrate", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_spec(*, path_prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [
        fixture_case("ordinary", 10, 7, 4),
        fixture_case("rhs-zero", 19, 0, 8),
        fixture_case("lp64-wrap", (1 << 64) - 2, 3, 12),
    ]
    initializer = {
        "record_type": "Ledger",
        "fields": [
            {"name": "total", "fixture_field": "initial_total", "rust_type": "usize"},
            {"name": "guard", "fixture_field": "owner_guard", "rust_type": "u32"},
            {
                "name": "slot",
                "record": {
                    "record_type": "Slot",
                    "fields": [
                        {"name": "amount", "fixture_field": "rhs_amount", "rust_type": "u32"},
                        {"name": "tag", "fixture_field": "slot_tag", "rust_type": "u32"},
                    ],
                },
            },
        ],
    }
    target_abi = {
        "triple_or_abi": "x86_64-unknown-linux-gnu",
        "endianness": "little",
        "int_width": 32,
        "long_width": 64,
        "pointer_width": 64,
        "size_t_width": 64,
    }
    spec = {
        "schema_version": 1,
        "target_id": "renamed-ledger",
        "slice_id": "owner-interior-usize-add",
        "level": "L3",
        "function_name": "accumulate_slot_amount",
        "source_commit": "owner-interior-usize-source",
        "c_source": renamed_c_source(),
        "fixture_contract": {
            "path": f"{path_prefix}fixtures/owner-interior-usize-add-cases.json",
            "behavior_fields": FIELDS,
            "observable_outputs": FIELDS,
            "cases": cases,
        },
        "replay_contract": {
            "schema_version": 1,
            "kind": "record_owner_interior_u32_to_usize_wrapping_add_state",
            "owner": {
                "parameter": "ledger",
                "c_type": "struct Ledger *",
                "rust_type": "Ledger",
                "pass_mode": "mutable_ref",
                "direction": "inout",
                "initializer": initializer,
            },
            "projection_path": ["slot"],
            "alias": {
                "local": "slot_view",
                "c_type": "SlotPtr",
                "rust_type": "Slot",
                "pass_mode": "mutable_ref",
            },
            "state_output": {
                "owner_field_path": ["total"],
                "fixture_field": "updated_total",
                "rust_type": "usize",
            },
            "rhs": {
                "alias_field_path": ["amount"],
                "owner_field_path": ["slot", "amount"],
                "rust_type": "u32",
                "mode": "direct_field_value",
            },
            "widening": {
                "conversion": "u32_to_usize",
                "source_rust_type": "u32",
                "target_rust_type": "usize",
                "source_bits": 32,
                "target_bits": 64,
                "signedness": "unsigned",
                "lossless": True,
                "target_abi_binding": "build_profile.target+c_boundary.target_abi_contract",
            },
            "state_update": {"operation": "wrapping_add"},
            "return": {"fixture_field": "accepted", "rust_type": "bool", "value": True},
            "noalias_required": [],
        },
        "c_boundary": {
            "oracle_source_mode": "embedded_slice_c_source",
            "signatures": [{
                "id": "sig-accumulate-slot-amount",
                "function": "accumulate_slot_amount",
                "return_type": "bool",
                "parameters": [{
                    "name": "ledger", "c_type": "struct Ledger *", "direction": "inout"
                }],
            }],
            "external_direct_callees": [],
            "direct_dependencies": [],
            "pointer_contract": {"aliasing_proven": True, "noalias_required": []},
            "target_abi_contract": dict(target_abi),
        },
        "build_profile": {
            "compiler": "cc",
            "include_paths": [],
            "defines": [],
            "oracle_harness_includes": [],
            "target": dict(target_abi),
        },
    }
    fixture = {
        "schema_version": 1,
        "level": "L3",
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "source_boundary": {"files": ["ledger.c"]},
        "compared_fields": FIELDS,
        "case_count": len(cases),
        "cases": cases,
    }
    return spec, fixture


def fixture_case(case_id: str, initial: int, rhs: int, tag: int) -> dict[str, Any]:
    return {
        "id": case_id,
        "inputs": {
            "initial_total": initial,
            "owner_guard": 31,
            "rhs_amount": rhs,
            "slot_tag": tag,
        },
        "expected_outputs": {
            "accepted": True,
            "updated_total": (initial + rhs) & 0xFFFFFFFFFFFFFFFF,
        },
    }


def renamed_c_source() -> str:
    return """#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
struct Slot { uint32_t amount; uint32_t tag; };
typedef struct Slot *SlotPtr;
struct Ledger { size_t total; uint32_t guard; struct Slot slot; };
static bool accumulate_slot_amount(struct Ledger *ledger)
{
    SlotPtr slot_view = &ledger->slot;
    ledger->total += slot_view->amount;
    return true;
}
"""


def renamed_rust_draft() -> str:
    return """#[derive(Clone, Copy)]
pub struct Slot { pub amount: u32, pub tag: u32 }
#[derive(Clone, Copy)]
pub struct Ledger { pub total: usize, pub guard: u32, pub slot: Slot }

pub fn accumulate_slot_amount(ledger: &mut Ledger) -> bool {
    let rhs = ledger.slot.amount;
    ledger.total = ledger.total.wrapping_add(rhs as usize);
    true
}
"""


def translation_carrier(c_source: str, source_file: str) -> dict[str, Any]:
    lines = c_source.splitlines(keepends=True)
    start = next(index for index, line in enumerate(lines, start=1) if line.startswith("static bool"))
    fragment = "".join(lines[start - 1 :])
    return {
        "kind": "exact_source_fragment_wrapper",
        "embedding_mode": "verbatim_once",
        "frontend_contract": "live_clang_slice_source",
        "source_text_normalization": "utf8_universal_newlines",
        "source_file_hash_mode": "raw_bytes",
        "artifact_source_hash_mode": "lf_stable_text",
        "carrier_function": "accumulate_slot_amount",
        "carrier_source_sha256": sha256_text(c_source),
        "claim_boundary": {
            "scope": "source_fragment_only",
            "whole_function_semantics_verified": False,
            "external_callee_semantics_verified": False,
            "excluded_semantics": ["surrounding whole-function behavior"],
        },
        "real_source": {
            "file": source_file,
            "containing_function": {
                "line_start": start,
                "line_end": len(lines),
                "hash_mode": "trimmed_normalized_span",
                "sha256": sha256_text(fragment.strip()),
                "declaration_text": "static bool accumulate_slot_amount(",
            },
            "fragment": {
                "line_start": start,
                "line_end": len(lines),
                "hash_mode": "normalized_line_span_with_newline",
                "sha256": sha256_text(fragment),
                "text": fragment,
            },
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
