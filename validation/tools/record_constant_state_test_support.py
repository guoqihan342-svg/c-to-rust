from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


FIELDS = ["was_cleared", "cleared_marker"]
REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("constant_state_auto_migrate", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_constant_state_spec(*, path_prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [
        constant_state_case("ordinary", 9, 47, 3),
        constant_state_case("maximum", 12, 0xFFFFFFFF, 88),
    ]
    initializer = {
        "record_type": "Parcel",
        "fields": [
            {"name": "label", "fixture_field": "parcel_label", "rust_type": "u32"},
            {
                "name": "route",
                "record": {
                    "record_type": "Route",
                    "fields": [
                        {"name": "marker", "fixture_field": "route_marker", "rust_type": "u32"},
                        {"name": "guard", "fixture_field": "route_guard", "rust_type": "u32"},
                    ],
                },
            },
        ],
    }
    spec = {
        "schema_version": 1,
        "target_id": "renamed-routing",
        "slice_id": "clear-nested-marker",
        "level": "L3",
        "function_name": "clear_nested_marker",
        "source_commit": "renamed-constant-state-source",
        "c_source": renamed_c_source(),
        "fixture_contract": {
            "path": f"{path_prefix}fixtures/constant-state-cases.json",
            "behavior_fields": FIELDS,
            "observable_outputs": FIELDS,
            "cases": cases,
        },
        "replay_contract": {
            "schema_version": 1,
            "kind": "record_u32_field_constant_state",
            "entry_arguments": [
                {
                    "parameter": "parcel",
                    "c_type": "struct Parcel *",
                    "rust_type": "Parcel",
                    "pass_mode": "mutable_ref",
                    "direction": "inout",
                    "initializer": initializer,
                }
            ],
            "state_output": {
                "parameter": "parcel",
                "field_path": ["route", "marker"],
                "fixture_field": "cleared_marker",
                "rust_type": "u32",
            },
            "state_update": {"operation": "constant_assign", "rust_type": "u32", "value": 0},
            "return": {"fixture_field": "was_cleared", "rust_type": "bool", "value": True},
            "noalias_required": [],
        },
        "c_boundary": {
            "oracle_source_mode": "embedded_slice_c_source",
            "signatures": [
                {
                    "id": "sig-clear-nested-marker",
                    "function": "clear_nested_marker",
                    "return_type": "bool",
                    "parameters": [
                        {"name": "parcel", "c_type": "struct Parcel *", "direction": "inout"}
                    ],
                }
            ],
            "external_direct_callees": [],
            "direct_dependencies": [],
            "pointer_contract": {"aliasing_proven": True, "noalias_required": []},
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
        "source_boundary": {"files": ["routing.c"]},
        "compared_fields": FIELDS,
        "case_count": len(cases),
        "cases": cases,
    }
    return spec, fixture


def constant_state_case(case_id: str, label: int, marker: int, guard: int) -> dict[str, Any]:
    return {
        "id": case_id,
        "inputs": {"parcel_label": label, "route_marker": marker, "route_guard": guard},
        "expected_outputs": {"was_cleared": True, "cleared_marker": 0},
    }


def renamed_c_source() -> str:
    return """struct Route { uint32_t marker; uint32_t guard; };
struct Parcel { uint32_t label; struct Route route; };
static bool clear_nested_marker(struct Parcel *parcel)
{
    parcel->route.marker = 0;
    return true;
}
"""


def renamed_rust_draft() -> str:
    return """#[derive(Clone, Copy)]
pub struct Route { pub marker: u32, pub guard: u32 }
#[derive(Clone, Copy)]
pub struct Parcel { pub label: u32, pub route: Route }

pub fn clear_nested_marker(parcel: &mut Parcel) -> bool {
    parcel.route.marker = 0;
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
        "carrier_function": "clear_nested_marker",
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
                "declaration_text": "static bool clear_nested_marker(",
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
