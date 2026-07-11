from __future__ import annotations

from typing import Any

from validation.tools._translation_carrier_reporter.call_continue_contract import KIND

from .constants import U32_MAX


def build_carrier_source(fragment: str) -> str:
    source = """#define FAILED_ADDR ((uint32_t)-1)
#define db_sec_size(db) ((db)->sec_size)
struct Database { uint32_t observed; uint32_t sec_size; };
struct Sector { uint32_t seed; uint32_t addr; };
struct Address { uint32_t start; };
struct Kv { struct Address addr; };
typedef struct Kv *fdb_kv_t;
struct Owner { struct Kv curr; uint32_t traversed_len; };
uint32_t get_next_kv_addr(struct Database *db, struct Sector *sector, struct Kv *kv);
static bool fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(struct Database *db, struct Sector sector_seed, uint32_t SECTOR_HDR_DATA_SIZE, struct Owner *itr)
{
    fdb_kv_t kv = &(itr->curr);
    struct Sector sector = sector_seed;
    bool run_once = true;
    while (run_once) {
        run_once = false;
FRAGMENT        return false;
    }
    return true;
}
"""
    if not fragment.endswith("\n"):
        raise ValueError("source fragment must end with one normalized newline")
    result = source.replace("FRAGMENT", fragment)
    if result.count(fragment) != 1:
        raise ValueError("source fragment must be embedded verbatim exactly once")
    return result


def build_replay_contract() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "kind": KIND,
        "entry_arguments": [
            record_entry(
                "db",
                "Database",
                "mutable_ref",
                [
                    scalar_field("observed", "db_observed_initial"),
                    scalar_field("sec_size", "db_add_rhs"),
                ],
            ),
            record_entry(
                "sector_seed",
                "Sector",
                "value",
                [
                    scalar_field("seed", "sector_seed"),
                    scalar_field("addr", "sector_addr"),
                ],
            ),
            {
                "parameter": "SECTOR_HDR_DATA_SIZE",
                "c_type": "uint32_t",
                "rust_type": "u32",
                "pass_mode": "value",
                "direction": "input",
                "fixture_field": "sector_header_data_size",
            },
            owner_entry(),
        ],
        "owner_parameter": "itr",
        "projection": {
            "path": ["curr"],
            "alias_local": "kv",
            "alias_c_pointer_type": "fdb_kv_t",
            "alias_rust_type": "Kv",
        },
        "external_callee": external_callee(),
        "comparison": {"operation": "eq", "rust_type": "u32", "sentinel": U32_MAX},
        "assigned_state": {
            "alias_field_path": ["addr", "start"],
            "owner_field_path": ["curr", "addr", "start"],
            "fixture_field": "alias_start_after",
            "rust_type": "u32",
        },
        "add_state": {
            "owner_field_path": ["traversed_len"],
            "fixture_field": "owner_traversed_after",
            "rust_type": "u32",
            "operation": "wrapping_add",
            "rhs": {
                "mode": "direct_record_u32_field",
                "parameter": "db",
                "field_path": ["sec_size"],
                "source_expression": "db_sec_size(db)",
            },
        },
        "zero_start": zero_start_contract(),
        "control_flow": {
            "kind": "single_iteration_while_call_compare_continue",
            "sentinel_local": "run_once",
            "initial_value": True,
            "body_first_assignment": False,
            "hit_reset_value": 0,
            "continue_target": "current_while",
            "miss_return": False,
            "terminal_return": True,
        },
        "return": {"fixture_field": "return_value", "rust_type": "bool"},
        "noalias_required": [["db", "itr"]],
    }


def record_entry(
    parameter: str,
    rust_type: str,
    pass_mode: str,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    pointer = " *" if pass_mode == "mutable_ref" else ""
    return {
        "parameter": parameter,
        "c_type": f"struct {rust_type}{pointer}",
        "rust_type": rust_type,
        "pass_mode": pass_mode,
        "direction": "inout" if pass_mode == "mutable_ref" else "input",
        "initializer": {"record_type": rust_type, "fields": fields},
    }


def scalar_field(name: str, fixture_field: str) -> dict[str, str]:
    return {"name": name, "fixture_field": fixture_field, "rust_type": "u32"}


def owner_entry() -> dict[str, Any]:
    address = {"record_type": "Address", "fields": [scalar_field("start", "alias_start_initial")]}
    kv = {"record_type": "Kv", "fields": [{"name": "addr", "record": address}]}
    return record_entry(
        "itr",
        "Owner",
        "mutable_ref",
        [
            {"name": "curr", "record": kv},
            scalar_field("traversed_len", "owner_traversed_initial"),
        ],
    )


def external_callee() -> dict[str, Any]:
    return {
        "name": "get_next_kv_addr",
        "return_fixture_field": "scripted_return",
        "call_count_output": "call_count",
        "arguments": [
            call_argument("entry_root", "db", "db", ["observed"], "call_db_observed"),
            call_argument(
                "entry_local_copy", "sector_seed", "sector", ["seed"], "call_sector_seed"
            ),
            call_argument(
                "owner_interior_alias", "itr", "kv", ["addr", "start"], "call_alias_start"
            ),
        ],
    }


def call_argument(
    mode: str,
    entry: str,
    callee: str,
    path: list[str],
    output: str,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "entry_parameter": entry,
        "callee_parameter": callee,
        "snapshot_field_path": path,
        "snapshot_output": output,
    }


def zero_start_contract() -> dict[str, Any]:
    return {
        "condition": {
            "target": "assigned_state",
            "operation": "eq",
            "value": 0,
            "rust_type": "u32",
        },
        "assignment": {
            "target": "assigned_state",
            "operation": "wrapping_add",
            "rust_type": "u32",
            "record": {
                "mode": "entry_record_u32_field",
                "parameter": "sector_seed",
                "field_path": ["addr"],
            },
            "offset": {"mode": "entry_u32_value", "parameter": "SECTOR_HDR_DATA_SIZE"},
        },
        "external_call": "skip",
        "else_path": "call_sentinel_reset_add_continue",
    }
