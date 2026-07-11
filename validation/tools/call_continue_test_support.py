from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from ._translation_carrier_reporter.call_continue_contract import parse_contract
from ._translation_carrier_reporter.call_continue_model import reference_outputs


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "validation/slice-specs/flashdb-real-fdb-kv-iterate-next-sector-advance-continue.json"


def renamed_spec() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spec = copy.deepcopy(json.loads(SPEC_PATH.read_text(encoding="utf-8")))
    spec["target_id"] = "orbit-store"
    spec["slice_id"] = "advance-window"
    spec["function_name"] = "advance_window"
    contract = spec["replay_contract"]
    entries = contract["entry_arguments"]
    _rename_entry(entries[0], "source", "Metrics", (("seen", "db_observed_initial"), ("step", "db_add_rhs")))
    _rename_entry(entries[1], "window_seed", "Window", (("tag", "sector_seed"),))
    entries[2]["parameter"] = "owner"
    entries[2]["c_type"] = "struct CursorOwner *"
    entries[2]["rust_type"] = "CursorOwner"
    entries[2]["initializer"] = {
        "record_type": "CursorOwner",
        "fields": [
            {"name": "active", "record": {"record_type": "Cell", "fields": [
                {"name": "meta", "record": {"record_type": "Meta", "fields": [
                    {"name": "phase", "fixture_field": "alias_start_initial", "rust_type": "u32"}
                ]}}
            ]}},
            {"name": "total", "fixture_field": "owner_traversed_initial", "rust_type": "u32"},
        ],
    }
    contract["owner_parameter"] = "owner"
    contract["projection"] = {
        "path": ["active"], "alias_local": "cursor",
        "alias_c_pointer_type": "CellPtr", "alias_rust_type": "Cell",
    }
    external = contract["external_callee"]
    external["name"] = "probe_next"
    external["arguments"] = [
        {"mode": "entry_root", "entry_parameter": "source", "callee_parameter": "metrics", "snapshot_field_path": ["seen"], "snapshot_output": "call_db_observed"},
        {"mode": "entry_local_copy", "entry_parameter": "window_seed", "callee_parameter": "window", "snapshot_field_path": ["tag"], "snapshot_output": "call_sector_seed"},
        {"mode": "owner_interior_alias", "entry_parameter": "owner", "callee_parameter": "cell", "snapshot_field_path": ["meta", "phase"], "snapshot_output": "call_alias_start"},
    ]
    contract["comparison"]["sentinel"] = 0xA5A5A5A5
    contract["assigned_state"]["alias_field_path"] = ["meta", "phase"]
    contract["assigned_state"]["owner_field_path"] = ["active", "meta", "phase"]
    contract["add_state"]["owner_field_path"] = ["total"]
    contract["add_state"]["rhs"].update(
        parameter="source", field_path=["step"], source_expression="source_step(source)"
    )
    contract["control_flow"]["sentinel_local"] = "once"
    contract["noalias_required"] = [["source", "owner"]]
    spec["c_boundary"]["pointer_contract"]["noalias_required"] = [["source", "owner"]]
    spec["c_boundary"]["signatures"] = [
        {"id": "sig-renamed-carrier", "function": "advance_window", "return_type": "bool", "parameters": [
            {"name": "source", "c_type": "struct Metrics *", "direction": "inout"},
            {"name": "window_seed", "c_type": "struct Window", "direction": "input"},
            {"name": "owner", "c_type": "struct CursorOwner *", "direction": "inout"},
        ]},
        {"id": "sig-renamed-external", "function": "probe_next", "return_type": "uint32_t", "parameters": [
            {"name": "metrics", "c_type": "struct Metrics *", "direction": "inout"},
            {"name": "window", "c_type": "struct Window *", "direction": "inout"},
            {"name": "cell", "c_type": "struct Cell *", "direction": "inout"},
        ]},
    ]
    spec["c_boundary"]["external_direct_callees"][0].update(
        name="probe_next", signature_ref="sig-renamed-external"
    )
    spec["c_source"] = renamed_c_source()
    spec["translation_carrier"]["carrier_source_sha256"] = hashlib.sha256(
        spec["c_source"].encode("utf-8")
    ).hexdigest()
    cases = renamed_cases()
    parsed = parse_contract(spec)
    for case in cases:
        case["expected_outputs"] = reference_outputs(case, parsed)
    for declared, case in zip(spec["fixture_contract"]["cases"], cases, strict=True):
        declared["id"] = case["id"]
        declared["inputs"] = case["inputs"]
        declared["expected_outputs"] = case["expected_outputs"]
    return spec, cases


def _rename_entry(
    entry: dict[str, Any], parameter: str, rust_type: str, fields: tuple[tuple[str, str], ...]
) -> None:
    entry["parameter"] = parameter
    entry["c_type"] = f"struct {rust_type} *" if entry["pass_mode"] == "mutable_ref" else f"struct {rust_type}"
    entry["rust_type"] = rust_type
    entry["initializer"] = {
        "record_type": rust_type,
        "fields": [
            {"name": name, "fixture_field": fixture, "rust_type": "u32"}
            for name, fixture in fields
        ],
    }


def renamed_cases() -> list[dict[str, Any]]:
    sentinel = 0xA5A5A5A5
    values = (
        ("hit-plain", 12, 13, 14, 15, 16, sentinel),
        ("hit-wrap", 21, 9, 22, 23, 0xFFFFFFFC, sentinel),
        ("miss-zero", 31, 32, 33, 34, 35, 0),
        ("miss-nonzero", 41, 42, 43, 44, 45, 6),
    )
    return [
        {
            "id": case_id,
            "inputs": {
                "db_observed_initial": seen,
                "db_add_rhs": step,
                "sector_seed": tag,
                "alias_start_initial": phase,
                "owner_traversed_initial": total,
                "scripted_return": scripted,
            },
        }
        for case_id, seen, step, tag, phase, total, scripted in values
    ]


def renamed_c_source() -> str:
    return """#define SOURCE_SENTINEL ((uint32_t)2779096485u)
#define source_step(source) ((source)->step)
struct Metrics { uint32_t seen; uint32_t step; };
struct Window { uint32_t tag; };
struct Meta { uint32_t phase; };
struct Cell { struct Meta meta; };
typedef struct Cell *CellPtr;
struct CursorOwner { struct Cell active; uint32_t total; };
uint32_t probe_next(struct Metrics *metrics, struct Window *window, struct Cell *cell);
static bool advance_window(struct Metrics *source, struct Window window_seed, struct CursorOwner *owner)
{
    CellPtr cursor = &(owner->active);
    struct Window window = window_seed;
    bool once = true;
    while (once) {
        once = false;
        if (0) {
        } else if ((cursor->meta.phase = probe_next(source, &window, cursor)) == 2779096485u) {
            cursor->meta.phase = 0;
            owner->total += source_step(source);
            continue;
        }
        return false;
    }
    return true;
}
"""


def renamed_rust_draft() -> str:
    return """#[derive(Clone, Copy)] struct Metrics { seen: u32, step: u32 }
#[derive(Clone, Copy)] struct Window { tag: u32 }
#[derive(Clone, Copy)] struct Meta { phase: u32 }
#[derive(Clone, Copy)] struct Cell { meta: Meta }
struct CursorOwner { active: Cell, total: u32 }
std::thread_local! {
    static RET: std::cell::Cell<u32> = std::cell::Cell::new(0);
    static COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static ARGS: std::cell::Cell<(u32,u32,u32)> = std::cell::Cell::new((0,0,0));
}
fn __c2r_scripted_external_set_return(value: u32) { RET.with(|slot| slot.set(value)); }
fn __c2r_scripted_external_reset_calls() { COUNT.with(|slot| slot.set(0)); ARGS.with(|slot| slot.set((0,0,0))); }
fn __c2r_scripted_external_call_count() -> usize { COUNT.with(std::cell::Cell::get) }
fn __c2r_scripted_external_call_args() -> (u32,u32,u32) { ARGS.with(std::cell::Cell::get) }
fn probe_next(metrics: &mut Metrics, window: &mut Window, cell: &mut Cell) -> u32 {
    ARGS.with(|slot| slot.set((metrics.seen, window.tag, cell.meta.phase)));
    COUNT.with(|slot| slot.set(slot.get() + 1));
    RET.with(std::cell::Cell::get)
}
fn advance_window(source: &mut Metrics, window_seed: Window, owner: &mut CursorOwner) -> bool {
    let cursor: &mut Cell = &mut owner.active;
    let mut window = window_seed;
    let mut once = true;
    while once {
        once = false;
        cursor.meta.phase = probe_next(source, &mut window, cursor);
        if cursor.meta.phase == 2779096485u32 {
            cursor.meta.phase = 0u32;
            owner.total = owner.total.wrapping_add(source.step);
            continue;
        }
        return false;
    }
    return true;
}
"""


def replay_source(cases: list[dict[str, Any]]) -> str:
    blocks = []
    for index, case in enumerate(cases):
        values = case["inputs"]
        expected = case["expected_outputs"]
        blocks.append(f"""
#[test]
fn replay_case_{index}() {{
    __c2r_scripted_external_set_return({values['scripted_return']}u32);
    __c2r_scripted_external_reset_calls();
    let mut source = Metrics {{ seen: {values['db_observed_initial']}u32, step: {values['db_add_rhs']}u32 }};
    let window = Window {{ tag: {values['sector_seed']}u32 }};
    let mut owner = CursorOwner {{ active: Cell {{ meta: Meta {{ phase: {values['alias_start_initial']}u32 }} }}, total: {values['owner_traversed_initial']}u32 }};
    let actual = advance_window(&mut source, window, &mut owner);
    assert_eq!(actual, {str(expected['return_value']).lower()});
    assert_eq!(owner.active.meta.phase, {expected['alias_start_after']}u32);
    assert_eq!(owner.total, {expected['owner_traversed_after']}u32);
}}
""")
    return "".join(blocks)


def renamed_target_only_rust_draft() -> str:
    source = renamed_rust_draft()
    definitions = "\n".join(source.splitlines()[:5]) + "\n"
    return definitions + source[source.index("fn advance_window"):]
