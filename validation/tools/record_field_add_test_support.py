from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


FIELDS = ["accepted", "combined_fill"]
REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("field_add_auto_migrate_under_test", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_field_add_spec(*, path_prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [
        field_add_case("ordinary", 17, 3, 9),
        field_add_case("u32-wrap", 0xFFFFFFF8, 5, 20),
    ]
    initializer = lambda record_type, fields: {"record_type": record_type, "fields": fields}
    spec = {
        "schema_version": 1,
        "target_id": "renamed-capacity",
        "slice_id": "merge-quota-field",
        "level": "L3",
        "function_name": "merge_quota",
        "source_commit": "renamed-field-add-source",
        "c_source": renamed_c_source(),
        "fixture_contract": {
            "path": f"{path_prefix}fixtures/field-add-cases.json",
            "behavior_fields": FIELDS,
            "observable_outputs": FIELDS,
            "cases": cases,
        },
        "replay_contract": {
            "schema_version": 1,
            "kind": "record_u32_field_wrapping_add_state",
            "entry_arguments": [
                {
                    "parameter": "reservoir",
                    "c_type": "struct Reservoir *",
                    "rust_type": "Reservoir",
                    "pass_mode": "mutable_ref",
                    "direction": "inout",
                    "initializer": initializer(
                        "Reservoir",
                        [
                            {"name": "fill", "fixture_field": "initial_fill", "rust_type": "u32"},
                            {"name": "tag", "fixture_field": "initial_tag", "rust_type": "u32"},
                        ],
                    ),
                },
                {
                    "parameter": "meter",
                    "c_type": "struct Meter *",
                    "rust_type": "Meter",
                    "pass_mode": "mutable_ref",
                    "direction": "input",
                    "initializer": initializer(
                        "Meter",
                        [
                            {"name": "quantum", "fixture_field": "meter_quantum", "rust_type": "u32"}
                        ],
                    ),
                },
            ],
            "rhs": {
                "parameter": "meter",
                "field_path": ["quantum"],
                "rust_type": "u32",
                "mode": "scalar_field_value",
            },
            "state_output": {
                "parameter": "reservoir",
                "field_path": ["fill"],
                "fixture_field": "combined_fill",
                "rust_type": "u32",
            },
            "state_update": {"operation": "wrapping_add"},
            "return": {"fixture_field": "accepted", "rust_type": "bool", "value": True},
            "noalias_required": [["reservoir", "meter"]],
        },
        "c_boundary": {
            "oracle_source_mode": "embedded_slice_c_source",
            "signatures": [
                {
                    "id": "sig-merge-quota",
                    "function": "merge_quota",
                    "return_type": "bool",
                    "parameters": [
                        {
                            "name": "reservoir",
                            "c_type": "struct Reservoir *",
                            "direction": "inout",
                        },
                        {
                            "name": "meter",
                            "c_type": "struct Meter *",
                            "direction": "input",
                        },
                    ],
                }
            ],
            "external_direct_callees": [],
            "direct_dependencies": [],
            "pointer_contract": {
                "aliasing_proven": True,
                "noalias_required": [["reservoir", "meter"]],
            },
        },
        "rust_boundary": {
            "public_api": [{"name": "merge_quota"}],
            "raw_pointer_policy": "internal_only",
        },
        "build_profile": {
            "compiler": "cc",
            "include_paths": [],
            "defines": [],
            "oracle_harness_includes": [],
        },
    }
    fixture = {
        "schema_version": 1,
        "level": "L3",
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "source_boundary": {"files": ["capacity.c"]},
        "compared_fields": FIELDS,
        "case_count": len(cases),
        "cases": cases,
    }
    return spec, fixture


def field_add_case(case_id: str, initial: int, tag: int, rhs: int) -> dict[str, Any]:
    return {
        "id": case_id,
        "inputs": {
            "initial_fill": initial,
            "initial_tag": tag,
            "meter_quantum": rhs,
        },
        "expected_outputs": {
            "accepted": True,
            "combined_fill": (initial + rhs) & 0xFFFFFFFF,
        },
    }


def renamed_c_source() -> str:
    return """struct Reservoir { uint32_t fill; uint32_t tag; };
struct Meter { uint32_t quantum; };
#define METER_QUANTUM(pointer) ((pointer)->quantum)
static bool merge_quota(struct Reservoir *reservoir, struct Meter *meter)
{
    reservoir->fill += METER_QUANTUM(meter);
    return true;
}
"""


def renamed_rust_draft() -> str:
    return """#[derive(Clone, Copy)]
pub struct Reservoir { pub fill: u32, pub tag: u32 }
#[derive(Clone, Copy)]
pub struct Meter { pub quantum: u32 }

pub fn merge_quota(reservoir: &mut Reservoir, meter: &mut Meter) -> bool {
    reservoir.fill = reservoir.fill.wrapping_add(meter.quantum);
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
        "carrier_function": "merge_quota",
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
                "declaration_text": "static bool merge_quota(",
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
