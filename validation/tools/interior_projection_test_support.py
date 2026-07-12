from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


FIELDS = ["was_reset", "observed_phase"]
REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("projection_auto_migrate", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_projection_spec(*, path_prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [
        projection_case("ordinary", 7, 11, 37, 5),
        projection_case("maximum", 19, 23, 0xFFFFFFFF, 41),
    ]
    initializer = {
        "record_type": "Owner",
        "fields": [
            {"name": "label", "fixture_field": "owner_label", "rust_type": "u32"},
            {
                "name": "current",
                "record": {
                    "record_type": "Node",
                    "fields": [
                        {
                            "name": "revision",
                            "fixture_field": "node_revision",
                            "rust_type": "u32",
                        },
                        {
                            "name": "telemetry",
                            "record": {
                                "record_type": "Telemetry",
                                "fields": [
                                    {
                                        "name": "phase",
                                        "fixture_field": "phase_value",
                                        "rust_type": "u32",
                                    },
                                    {
                                        "name": "guard",
                                        "fixture_field": "phase_guard",
                                        "rust_type": "u32",
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
        ],
    }
    spec = {
        "schema_version": 1,
        "target_id": "renamed-owner-projection",
        "slice_id": "reset-current-phase",
        "level": "L3",
        "function_name": "reset_current_phase",
        "source_commit": "renamed-owner-projection-source",
        "c_source": renamed_c_source(),
        "fixture_contract": {
            "path": f"{path_prefix}fixtures/projection-cases.json",
            "behavior_fields": FIELDS,
            "observable_outputs": FIELDS,
            "cases": cases,
        },
        "replay_contract": {
            "schema_version": 1,
            "kind": "record_interior_projection_u32_constant_state",
            "owner": {
                "parameter": "owner",
                "c_type": "struct Owner *",
                "rust_type": "Owner",
                "pass_mode": "mutable_ref",
                "direction": "inout",
                "initializer": initializer,
            },
            "projection_path": ["current"],
            "alias": {
                "local": "cursor",
                "c_pointer_type": "NodeCursor",
                "rust_type": "Node",
            },
            "state_output": {
                "alias_field_path": ["telemetry", "phase"],
                "owner_field_path": ["current", "telemetry", "phase"],
                "fixture_field": "observed_phase",
                "rust_type": "u32",
            },
            "constant_assign": {"rust_type": "u32", "value": 0},
            "return": {"fixture_field": "was_reset", "rust_type": "bool", "value": True},
            "noalias_required": [],
        },
        "c_boundary": {
            "oracle_source_mode": "embedded_slice_c_source",
            "signatures": [
                {
                    "id": "sig-reset-current-phase",
                    "function": "reset_current_phase",
                    "return_type": "bool",
                    "parameters": [
                        {"name": "owner", "c_type": "struct Owner *", "direction": "inout"}
                    ],
                }
            ],
            "external_direct_callees": [],
            "direct_dependencies": [],
            "pointer_contract": {"aliasing_proven": True, "noalias_required": []},
        },
        "rust_boundary": {
            "public_api": [{"name": "reset_current_phase"}],
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
        "source_boundary": {"files": ["owner_projection.c"]},
        "compared_fields": FIELDS,
        "case_count": len(cases),
        "cases": cases,
    }
    return spec, fixture


def projection_case(
    case_id: str, label: int, revision: int, phase: int, guard: int
) -> dict[str, Any]:
    return {
        "id": case_id,
        "inputs": {
            "owner_label": label,
            "node_revision": revision,
            "phase_value": phase,
            "phase_guard": guard,
        },
        "expected_outputs": {"was_reset": True, "observed_phase": 0},
    }


def renamed_c_source() -> str:
    return """struct Telemetry { uint32_t phase; uint32_t guard; };
struct Node { uint32_t revision; struct Telemetry telemetry; };
struct Owner { uint32_t label; struct Node current; };
typedef struct Node *NodeCursor;
static bool reset_current_phase(struct Owner *owner)
{
    NodeCursor cursor = &(owner->current);
    cursor->telemetry.phase = 0;
    return true;
}
"""


def renamed_rust_draft(*, explicit_type: bool = False) -> str:
    annotation = ": &mut Node" if explicit_type else ""
    return f"""pub struct Telemetry {{ pub phase: u32, pub guard: u32 }}
pub struct Node {{ pub revision: u32, pub telemetry: Telemetry }}
pub struct Owner {{ pub label: u32, pub current: Node }}

pub fn reset_current_phase(owner: &mut Owner) -> bool {{
    let cursor{annotation} = &mut owner.current;
    cursor.telemetry.phase = (0i32 as u32);
    true
}}
"""


def unsafe_rust_draft() -> str:
    return """pub struct Telemetry { pub phase: u32, pub guard: u32 }
pub struct Node { pub revision: u32, pub telemetry: Telemetry }
pub struct Owner { pub label: u32, pub current: Node }

pub fn reset_current_phase(owner: &mut Owner) -> bool {
    let cursor: *mut Node = &mut owner.current;
    unsafe { (*cursor).telemetry.phase = 0; }
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
        "carrier_function": "reset_current_phase",
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
                "declaration_text": "static bool reset_current_phase(",
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
