from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SENTINEL = 91
FIELDS = ["completed", "selected_value", "probe_count", "probe_args"]


def build_sequence_spec(*, path_prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [
        sequence_case("marker-first", 17, 23, 31, 4, [SENTINEL]),
        sequence_case("marker-later", 7, 11, 13, 2, [5, 8, SENTINEL]),
    ]
    leaf = lambda record_type, fields: {"record_type": record_type, "fields": fields}
    spec = {
        "schema_version": 1,
        "target_id": "renamed-ledger",
        "slice_id": "advance-window-tail",
        "level": "L3",
        "function_name": "advance_window_tail",
        "source_commit": "renamed-sequence-source",
        "c_source": renamed_c_source(),
        "fixture_contract": {
            "path": f"{path_prefix}fixtures/window-tail-cases.json",
            "behavior_fields": FIELDS,
            "observable_outputs": FIELDS,
            "cases": cases,
        },
        "replay_contract": {
            "schema_version": 1,
            "kind": "scripted_external_record_u32_sequence_do_while_state",
            "external_callee": {
                "name": "probe_following_window",
                "return_sequence_fixture_field": "probe_sequence",
                "call_count_output": "probe_count",
                "call_args_output": "probe_args",
                "arguments": [
                    {
                        "parameter": "ledger_ref",
                        "mode": "record_ref",
                        "entry_parameter": "ledger",
                        "field_path": ["stamp"],
                    },
                    {
                        "parameter": "window_ref",
                        "mode": "record_ref",
                        "entry_parameter": "window_seed",
                        "field_path": ["page"],
                    },
                    {
                        "parameter": "walked_copy",
                        "mode": "scalar_field_value",
                        "entry_parameter": "progress",
                        "field_path": ["walked"],
                    },
                ],
            },
            "entry_arguments": [
                {
                    "parameter": "ledger",
                    "c_type": "struct Ledger *",
                    "rust_type": "Ledger",
                    "pass_mode": "mutable_ref",
                    "direction": "input",
                    "initializer": leaf(
                        "Ledger",
                        [{"name": "stamp", "fixture_field": "ledger_stamp", "rust_type": "u32"}],
                    ),
                },
                {
                    "parameter": "window_seed",
                    "c_type": "struct Window",
                    "rust_type": "Window",
                    "pass_mode": "value",
                    "direction": "input",
                    "initializer": leaf(
                        "Window",
                        [{"name": "page", "fixture_field": "window_page", "rust_type": "u32"}],
                    ),
                },
                {
                    "parameter": "progress",
                    "c_type": "struct Progress *",
                    "rust_type": "Progress",
                    "pass_mode": "mutable_ref",
                    "direction": "inout",
                    "initializer": leaf(
                        "Progress",
                        [
                            {"name": "walked", "fixture_field": "walked", "rust_type": "u32"},
                            {"name": "selected", "fixture_field": "selected_initial", "rust_type": "u32"},
                        ],
                    ),
                },
            ],
            "state_output": {
                "parameter": "progress",
                "field_path": ["selected"],
                "fixture_field": "selected_value",
                "rust_type": "u32",
            },
            "loop": {"sentinel": SENTINEL, "comparison": "not_equal", "max_calls": 5},
            "return": {"fixture_field": "completed", "rust_type": "bool", "value": True},
            "noalias_required": [["ledger", "progress"]],
        },
        "c_boundary": {
            "oracle_source_mode": "embedded_slice_c_source",
            "signatures": [
                {
                    "id": "sig-advance-window-tail",
                    "function": "advance_window_tail",
                    "return_type": "bool",
                    "parameters": [
                        {"name": "ledger", "c_type": "struct Ledger *", "direction": "input"},
                        {"name": "window_seed", "c_type": "struct Window", "direction": "input"},
                        {"name": "progress", "c_type": "struct Progress *", "direction": "inout"},
                    ],
                },
                {
                    "id": "sig-probe-following-window",
                    "function": "probe_following_window",
                    "return_type": "uint32_t",
                    "parameters": [
                        {"name": "ledger_ref", "c_type": "struct Ledger *", "direction": "input"},
                        {"name": "window_ref", "c_type": "struct Window *", "direction": "input"},
                        {"name": "walked_copy", "c_type": "uint32_t", "direction": "input"},
                    ],
                    "definition_status": "deterministic_fixture_stimulus",
                },
            ],
            "external_direct_callees": [
                {
                    "name": "probe_following_window",
                    "signature_ref": "sig-probe-following-window",
                    "definition_status": "deterministic_fixture_stimulus",
                    "stub_boundary": "scripted_fixture_only_no_real_callee_semantics",
                }
            ],
            "direct_dependencies": [
                {
                    "kind": "callee",
                    "name": "probe_following_window",
                    "definition_status": "deterministic_fixture_stimulus_only",
                }
            ],
            "pointer_contract": {
                "aliasing_proven": True,
                "noalias_required": [["ledger", "progress"]],
            },
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
        "source_boundary": {"files": ["tail.c"]},
        "compared_fields": FIELDS,
        "case_count": len(cases),
        "cases": cases,
    }
    return spec, fixture


def build_interior_sequence_spec(
    *, path_prefix: str = ""
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec, fixture = build_sequence_spec(path_prefix=path_prefix)
    fields = spec["replay_contract"]["entry_arguments"][2]["initializer"]["fields"]
    fields[1] = {
        "name": "current",
        "record": {
            "record_type": "Cursor",
            "fields": [
                {
                    "name": "selected",
                    "fixture_field": "selected_initial",
                    "rust_type": "u32",
                },
                {"name": "tag", "fixture_field": "cursor_tag", "rust_type": "u32"},
            ],
        },
    }
    spec["replay_contract"]["external_callee"]["arguments"][2] = {
        "parameter": "cursor_ref",
        "mode": "owner_interior_alias",
        "entry_parameter": "progress",
        "projection_path": ["current"],
        "alias_local": "cursor",
        "field_path": ["selected"],
    }
    spec["replay_contract"]["schema_version"] = 2
    spec["replay_contract"]["state_output"]["field_path"] = ["current", "selected"]
    spec["replay_contract"]["return"]["value"] = False
    spec["c_boundary"]["signatures"][1]["parameters"][2] = {
        "name": "cursor_ref",
        "c_type": "struct Cursor *",
        "direction": "inout",
    }
    spec["c_source"] = renamed_interior_c_source()
    for case in spec["fixture_contract"]["cases"]:
        inputs = case["inputs"]
        inputs["cursor_tag"] = 101 + len(case["id"])
        expected = case["expected_outputs"]
        expected["completed"] = False
        current = inputs["selected_initial"]
        rows = []
        for scripted in inputs["probe_sequence"]:
            rows.append([inputs["ledger_stamp"], inputs["window_page"], current])
            current = scripted
            if scripted == SENTINEL:
                break
        expected["probe_args"] = rows
    fixture["cases"] = spec["fixture_contract"]["cases"]
    return spec, fixture


def sequence_case(
    case_id: str,
    ledger_stamp: int,
    window_page: int,
    walked: int,
    selected_initial: int,
    sequence: list[int],
) -> dict[str, Any]:
    count = sequence.index(SENTINEL) + 1
    row = [ledger_stamp, window_page, walked]
    return {
        "id": case_id,
        "inputs": {
            "ledger_stamp": ledger_stamp,
            "window_page": window_page,
            "walked": walked,
            "selected_initial": selected_initial,
            "probe_sequence": sequence,
        },
        "expected_outputs": {
            "completed": True,
            "selected_value": SENTINEL,
            "probe_count": count,
            "probe_args": [list(row) for _ in range(count)],
        },
    }


def renamed_c_source() -> str:
    return """#define WINDOW_END 91u
struct Ledger { uint32_t stamp; };
struct Window { uint32_t page; };
struct Progress { uint32_t walked; uint32_t selected; };
uint32_t probe_following_window(struct Ledger *ledger_ref, struct Window *window_ref, uint32_t walked_copy);
static bool advance_window_tail(struct Ledger *ledger, struct Window window_seed, struct Progress *progress)
{
    struct Window window = window_seed;
    do {
        uint32_t walked_copy = progress->walked;
        progress->selected = probe_following_window(ledger, &window, walked_copy);
    } while (progress->selected != WINDOW_END);
    return true;
}
"""


def renamed_rust_draft() -> str:
    return """#[derive(Clone, Copy)]
pub struct Ledger { pub stamp: u32 }
#[derive(Clone, Copy)]
pub struct Window { pub page: u32 }
#[derive(Clone, Copy)]
pub struct Progress { pub walked: u32, pub selected: u32 }

pub fn advance_window_tail(ledger: &mut Ledger, window_seed: Window, progress: &mut Progress) -> bool {
    let mut window = window_seed;
    loop {
        let walked_copy = progress.walked;
        progress.selected = probe_following_window(ledger, &mut window, walked_copy);
        if progress.selected != 91u32 {
            continue;
        }
        break;
    }
    true
}
"""


def renamed_interior_c_source() -> str:
    return """#define WINDOW_END 91u
struct Ledger { uint32_t stamp; };
struct Window { uint32_t page; };
struct Cursor { uint32_t selected; uint32_t tag; };
struct Progress { uint32_t walked; struct Cursor current; };
uint32_t probe_following_window(struct Ledger *ledger_ref, struct Window *window_ref, struct Cursor *cursor_ref);
static bool advance_window_tail(struct Ledger *ledger, struct Window window_seed, struct Progress *progress)
{
    struct Cursor *cursor = &progress->current;
    struct Window window = window_seed;
    bool run_once = true;
    while (run_once) {
        run_once = false;
        do {
        } while ((cursor->selected = probe_following_window(ledger, &window, cursor)) != WINDOW_END);
        return false;
    }
    return true;
}
"""


def renamed_interior_rust_draft() -> str:
    return """#[derive(Clone, Copy)]
pub struct Ledger { pub stamp: u32 }
#[derive(Clone, Copy)]
pub struct Window { pub page: u32 }
#[derive(Clone, Copy)]
pub struct Cursor { pub selected: u32, pub tag: u32 }
#[derive(Clone, Copy)]
pub struct Progress { pub walked: u32, pub current: Cursor }

pub fn advance_window_tail(ledger: &mut Ledger, window_seed: Window, progress: &mut Progress) -> bool {
    let cursor = &mut progress.current;
    let mut window = window_seed;
    loop {
        cursor.selected = probe_following_window(ledger, &mut window, cursor);
        if !(cursor.selected != 91u32) {
            break;
        }
    }
    false
}
"""


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))
