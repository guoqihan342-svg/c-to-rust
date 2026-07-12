from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


FIELDS = ["completed", "updated_count"]
REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("postfix_increment_auto_migrate", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_postfix_increment_spec(*, path_prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [
        postfix_increment_case("zero", 0),
        postfix_increment_case("ordinary", 41),
        postfix_increment_case("u32-wrap", 0xFFFFFFFF),
    ]
    initializer = {
        "record_type": "CounterBox",
        "fields": [
            {"name": "ticks", "fixture_field": "initial_count", "rust_type": "u32"}
        ],
    }
    spec = {
        "schema_version": 1,
        "target_id": "renamed-counter",
        "slice_id": "bump-counter",
        "level": "L3",
        "function_name": "bump_counter",
        "source_commit": "renamed-postfix-source",
        "c_source": renamed_c_source(),
        "fixture_contract": {
            "path": f"{path_prefix}fixtures/postfix-increment-cases.json",
            "behavior_fields": FIELDS,
            "observable_outputs": FIELDS,
            "cases": cases,
        },
        "replay_contract": {
            "schema_version": 1,
            "kind": "record_u32_field_postfix_increment_state",
            "entry_arguments": [
                {
                    "parameter": "counter",
                    "c_type": "struct CounterBox *",
                    "rust_type": "CounterBox",
                    "pass_mode": "mutable_ref",
                    "direction": "inout",
                    "initializer": initializer,
                }
            ],
            "state_output": {
                "parameter": "counter",
                "field_path": ["ticks"],
                "fixture_field": "updated_count",
                "rust_type": "u32",
            },
            "state_update": {"operation": "wrapping_add", "increment": 1},
            "return": {"fixture_field": "completed", "rust_type": "bool", "value": True},
            "noalias_required": [],
        },
        "c_boundary": {
            "oracle_source_mode": "embedded_slice_c_source",
            "signatures": [
                {
                    "id": "sig-bump-counter",
                    "function": "bump_counter",
                    "return_type": "bool",
                    "parameters": [
                        {
                            "name": "counter",
                            "c_type": "struct CounterBox *",
                            "direction": "inout",
                        }
                    ],
                }
            ],
            "external_direct_callees": [],
            "direct_dependencies": [],
            "pointer_contract": {"aliasing_proven": True, "noalias_required": []},
        },
        "rust_boundary": {
            "public_api": [{"name": "bump_counter"}],
            "raw_pointer_policy": "internal_only",
        },
        "build_profile": {
            "compiler": "cc", "include_paths": [], "defines": [],
            "oracle_harness_includes": [],
        },
    }
    fixture = {
        "schema_version": 1,
        "level": "L3",
        "target_id": spec["target_id"],
        "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"],
        "source_boundary": {"files": ["counter.c"]},
        "compared_fields": FIELDS,
        "case_count": len(cases),
        "cases": cases,
    }
    return spec, fixture


def postfix_increment_case(case_id: str, initial: int) -> dict[str, Any]:
    return {
        "id": case_id,
        "inputs": {"initial_count": initial},
        "expected_outputs": {
            "completed": True,
            "updated_count": (initial + 1) & 0xFFFFFFFF,
        },
    }


def renamed_c_source() -> str:
    return """struct CounterBox { uint32_t ticks; };
static bool bump_counter(struct CounterBox *counter)
{
    counter->ticks++;
    return true;
}
"""


def renamed_rust_draft() -> str:
    return """#[derive(Clone, Copy)]
pub struct CounterBox { pub ticks: u32 }

pub fn bump_counter(counter: &mut CounterBox) -> bool {
    counter.ticks = counter.ticks.wrapping_add(1u32);
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
        "carrier_function": "bump_counter",
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
                "declaration_text": "static bool bump_counter(",
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
