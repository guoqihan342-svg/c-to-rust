from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


FIELDS = ["accepted", "updated_visits", "updated_bytes", "updated_payload"]
REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("stats_sequence_auto_migrate", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_spec(*, path_prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [
        fixture_case("ordinary", 4, 10, 20, 3, 7),
        fixture_case("zero-rhs", 8, 42, 99, 0, 0),
        fixture_case("all-wrap", 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFE, 0xFFFFFFFFFFFFFFFD, 3, 5),
        fixture_case("source-discriminator", 17, 100, 200, 1, 9),
    ]
    initializer = {
        "record_type": "Tally",
        "fields": [
            {"name": "visits", "fixture_field": "initial_visits", "rust_type": "u32"},
            {
                "name": "cell",
                "record": {
                    "record_type": "Cell",
                    "fields": [
                        {"name": "alpha", "fixture_field": "alpha_value", "rust_type": "u32"},
                        {"name": "beta", "fixture_field": "beta_value", "rust_type": "u32"},
                    ],
                },
            },
            {"name": "bytes", "fixture_field": "initial_bytes", "rust_type": "usize"},
            {"name": "payload", "fixture_field": "initial_payload", "rust_type": "usize"},
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
    widening = {
        "conversion": "u32_to_usize",
        "source_rust_type": "u32",
        "target_rust_type": "usize",
        "source_bits": 32,
        "target_bits": 64,
        "signedness": "unsigned",
        "lossless": True,
        "target_abi_binding": "build_profile.target+c_boundary.target_abi_contract",
    }
    spec = {
        "schema_version": 1,
        "target_id": "renamed-tally",
        "slice_id": "owner-interior-stats-sequence",
        "level": "L3",
        "function_name": "apply_stats",
        "source_commit": "stats-sequence-source",
        "c_source": renamed_c_source(),
        "fixture_contract": {
            "path": f"{path_prefix}fixtures/stats-sequence-cases.json",
            "behavior_fields": FIELDS,
            "observable_outputs": FIELDS,
            "cases": cases,
        },
        "replay_contract": {
            "schema_version": 1,
            "kind": "record_owner_interior_stats_sequence_state",
            "owner": {
                "parameter": "tally",
                "c_type": "struct Tally *",
                "rust_type": "Tally",
                "pass_mode": "mutable_ref",
                "direction": "inout",
                "initializer": initializer,
            },
            "projection_path": ["cell"],
            "alias": {
                "local": "view",
                "c_type": "CellPtr",
                "rust_type": "Cell",
                "pass_mode": "mutable_ref",
            },
            "updates": [
                {
                    "operation": "postfix_increment",
                    "target": {
                        "owner_field_path": ["visits"],
                        "fixture_field": "updated_visits",
                        "rust_type": "u32",
                    },
                    "increment": 1,
                },
                {
                    "operation": "wrapping_add",
                    "target": {
                        "owner_field_path": ["bytes"],
                        "fixture_field": "updated_bytes",
                        "rust_type": "usize",
                    },
                    "source": {
                        "alias_field_path": ["alpha"],
                        "owner_field_path": ["cell", "alpha"],
                        "rust_type": "u32",
                        "mode": "direct_field_value",
                    },
                    "widening": dict(widening),
                },
                {
                    "operation": "wrapping_add",
                    "target": {
                        "owner_field_path": ["payload"],
                        "fixture_field": "updated_payload",
                        "rust_type": "usize",
                    },
                    "source": {
                        "alias_field_path": ["beta"],
                        "owner_field_path": ["cell", "beta"],
                        "rust_type": "u32",
                        "mode": "direct_field_value",
                    },
                    "widening": dict(widening),
                },
            ],
            "return": {"fixture_field": "accepted", "rust_type": "bool", "value": True},
            "noalias_required": [],
        },
        "c_boundary": {
            "oracle_source_mode": "embedded_slice_c_source",
            "signatures": [{
                "id": "sig-apply-stats",
                "function": "apply_stats",
                "return_type": "bool",
                "parameters": [{
                    "name": "tally", "c_type": "struct Tally *", "direction": "inout"
                }],
            }],
            "external_direct_callees": [],
            "direct_dependencies": [],
            "pointer_contract": {"aliasing_proven": True, "noalias_required": []},
            "target_abi_contract": dict(target_abi),
        },
        "rust_boundary": {
            "public_api": [{"name": "apply_stats"}],
            "raw_pointer_policy": "internal_only",
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
        "source_boundary": {"files": ["stats.c"]},
        "compared_fields": FIELDS,
        "case_count": len(cases),
        "cases": cases,
    }
    return spec, fixture


def fixture_case(
    case_id: str, visits: int, initial_bytes: int, initial_payload: int, alpha: int, beta: int
) -> dict[str, Any]:
    return {
        "id": case_id,
        "inputs": {
            "initial_visits": visits,
            "alpha_value": alpha,
            "beta_value": beta,
            "initial_bytes": initial_bytes,
            "initial_payload": initial_payload,
        },
        "expected_outputs": {
            "accepted": True,
            "updated_visits": (visits + 1) & 0xFFFFFFFF,
            "updated_bytes": (initial_bytes + alpha) & 0xFFFFFFFFFFFFFFFF,
            "updated_payload": (initial_payload + beta) & 0xFFFFFFFFFFFFFFFF,
        },
    }


def renamed_c_source() -> str:
    return """#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
struct Cell { uint32_t alpha; uint32_t beta; };
typedef struct Cell *CellPtr;
struct Tally { uint32_t visits; struct Cell cell; size_t bytes; size_t payload; };
static bool apply_stats(struct Tally *tally)
{
    CellPtr view = &tally->cell;
    tally->visits++;
    tally->bytes += view->alpha;
    tally->payload += view->beta;
    return true;
}
"""


def renamed_rust_draft() -> str:
    return """#[derive(Clone, Copy)]
pub struct Cell { pub alpha: u32, pub beta: u32 }
#[derive(Clone, Copy)]
pub struct Tally { pub visits: u32, pub cell: Cell, pub bytes: usize, pub payload: usize }

pub fn apply_stats(tally: &mut Tally) -> bool {
    let alpha = tally.cell.alpha;
    let beta = tally.cell.beta;
    tally.visits = tally.visits.wrapping_add(1u32);
    tally.bytes = tally.bytes.wrapping_add(alpha as usize);
    tally.payload = tally.payload.wrapping_add(beta as usize);
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
        "carrier_function": "apply_stats",
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
                "declaration_text": "static bool apply_stats(",
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
