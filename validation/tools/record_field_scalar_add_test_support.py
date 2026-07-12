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
    spec = importlib.util.spec_from_file_location("field_scalar_add_auto_migrate", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_field_scalar_add_spec(*, path_prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [
        field_scalar_add_case("ordinary", 31, 8, 17, 4, 5),
        field_scalar_add_case("carry", 7, 2, 1, 9, 3),
        field_scalar_add_case("u32-wrap", 99, 6, 0xFFFFFFF8, 12, 20),
    ]
    harbor_initializer = {
        "record_type": "Harbor",
        "fields": [
            {"name": "label", "fixture_field": "harbor_label", "rust_type": "u32"},
            {
                "name": "slot",
                "record": {
                    "record_type": "Slot",
                    "fields": [
                        {"name": "total", "fixture_field": "initial_total", "rust_type": "u32"},
                        {"name": "guard", "fixture_field": "slot_guard", "rust_type": "u32"},
                    ],
                },
            },
        ],
    }
    sample_initializer = {
        "record_type": "Sample",
        "fields": [
            {"name": "amount", "fixture_field": "sample_amount", "rust_type": "u32"},
            {"name": "tag", "fixture_field": "sample_tag", "rust_type": "u32"},
        ],
    }
    spec = {
        "schema_version": 1,
        "target_id": "renamed-harbor",
        "slice_id": "assign-field-scalar-sum",
        "level": "L3",
        "function_name": "assign_field_scalar_sum",
        "source_commit": "renamed-field-scalar-source",
        "c_source": renamed_c_source(),
        "fixture_contract": {
            "path": f"{path_prefix}fixtures/field-scalar-add-cases.json",
            "behavior_fields": FIELDS,
            "observable_outputs": FIELDS,
            "cases": cases,
        },
        "replay_contract": {
            "schema_version": 1,
            "kind": "record_u32_field_scalar_wrapping_add_state",
            "entry_arguments": [
                {
                    "parameter": "harbor",
                    "c_type": "struct Harbor *",
                    "rust_type": "Harbor",
                    "pass_mode": "mutable_ref",
                    "direction": "inout",
                    "initializer": harbor_initializer,
                },
                {
                    "parameter": "sample",
                    "c_type": "struct Sample",
                    "rust_type": "Sample",
                    "pass_mode": "value",
                    "direction": "input",
                    "initializer": sample_initializer,
                },
                {
                    "parameter": "increment",
                    "c_type": "uint32_t",
                    "rust_type": "u32",
                    "pass_mode": "value",
                    "direction": "input",
                    "fixture_field": "increment_value",
                },
            ],
            "state_output": {
                "parameter": "harbor",
                "field_path": ["slot", "total"],
                "fixture_field": "updated_total",
                "rust_type": "u32",
            },
            "state_update": {
                "operation": "wrapping_add",
                "record_field": {
                    "parameter": "sample",
                    "field_path": ["amount"],
                    "rust_type": "u32",
                    "mode": "direct_field_value",
                },
                "scalar": {
                    "parameter": "increment",
                    "fixture_field": "increment_value",
                    "rust_type": "u32",
                    "mode": "scalar_value",
                },
            },
            "return": {"fixture_field": "accepted", "rust_type": "bool", "value": False},
            "noalias_required": [],
        },
        "c_boundary": {
            "oracle_source_mode": "embedded_slice_c_source",
            "signatures": [
                {
                    "id": "sig-assign-field-scalar-sum",
                    "function": "assign_field_scalar_sum",
                    "return_type": "bool",
                    "parameters": [
                        {"name": "harbor", "c_type": "struct Harbor *", "direction": "inout"},
                        {"name": "sample", "c_type": "struct Sample", "direction": "input"},
                        {"name": "increment", "c_type": "uint32_t", "direction": "input"},
                    ],
                }
            ],
            "external_direct_callees": [],
            "direct_dependencies": [],
            "pointer_contract": {"aliasing_proven": True, "noalias_required": []},
        },
        "rust_boundary": {
            "public_api": [{"name": "assign_field_scalar_sum"}],
            "raw_pointer_policy": "internal_only",
        },
        "build_profile": {
            "compiler": "cc", "include_paths": [], "defines": [], "oracle_harness_includes": []
        },
    }
    fixture = {
        "schema_version": 1,
        "level": "L3",
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "source_boundary": {"files": ["harbor.c"]},
        "compared_fields": FIELDS,
        "case_count": len(cases),
        "cases": cases,
    }
    return spec, fixture


def field_scalar_add_case(
    case_id: str, initial: int, guard: int, amount: int, tag: int, increment: int
) -> dict[str, Any]:
    return {
        "id": case_id,
        "inputs": {
            "harbor_label": 42,
            "initial_total": initial,
            "slot_guard": guard,
            "sample_amount": amount,
            "sample_tag": tag,
            "increment_value": increment,
        },
        "expected_outputs": {
            "accepted": False,
            "updated_total": (amount + increment) & 0xFFFFFFFF,
        },
    }


def renamed_c_source() -> str:
    return """struct Slot { uint32_t total; uint32_t guard; };
struct Harbor { uint32_t label; struct Slot slot; };
struct Sample { uint32_t amount; uint32_t tag; };
static bool assign_field_scalar_sum(
    struct Harbor *harbor, struct Sample sample, uint32_t increment)
{
    harbor->slot.total = sample.amount + increment;
    return false;
}
"""


def renamed_rust_draft() -> str:
    return """#[derive(Clone, Copy)]
pub struct Slot { pub total: u32, pub guard: u32 }
#[derive(Clone, Copy)]
pub struct Harbor { pub label: u32, pub slot: Slot }
#[derive(Clone, Copy)]
pub struct Sample { pub amount: u32, pub tag: u32 }

pub fn assign_field_scalar_sum(harbor: &mut Harbor, sample: Sample, increment: u32) -> bool {
    harbor.slot.total = sample.amount.wrapping_add(increment);
    false
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
        "carrier_function": "assign_field_scalar_sum",
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
                "line_start": start, "line_end": len(lines),
                "hash_mode": "trimmed_normalized_span", "sha256": sha256_text(fragment.strip()),
                "declaration_text": "static bool assign_field_scalar_sum(",
            },
            "fragment": {
                "line_start": start, "line_end": len(lines),
                "hash_mode": "normalized_line_span_with_newline", "sha256": sha256_text(fragment),
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
