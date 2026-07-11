from typing import Any


def build_memory_model() -> dict[str, Any]:
    return {
        "alias_contract": {
            "decision": "requires_noalias_contract",
            "proven": True,
            "requires_noalias": True,
            "complete_alias_safety": True,
            "source": "db and itr are distinct mutable roots; kv is a scoped interior mutable reborrow of itr.curr and sector is a local value copy.",
        },
        "ownership_contract": {
            "inputs": [
                "fixture-created Database, Sector, header-size, and Owner values",
                "scripted external-call return value",
            ],
            "outputs": [
                "carrier return value",
                "external-call snapshots",
                "itr.curr.addr.start",
                "itr.traversed_len",
            ],
            "borrow_model": "one mutable Database root, one mutable Owner root, one local Sector copy, and a scoped interior projection from itr to curr",
            "unsafe_boundary": "No raw pointer is emitted; the explicit db/itr noalias pair is required.",
        },
        "length_companions": [],
        "effect_graph": {
            "effects": effects(),
            "edges": edges(),
            "summary": {
                "reads": [
                    "db.observed",
                    "db.sec_size",
                    "sector.seed",
                    "sector.addr",
                    "sector_header_data_size",
                    "itr.curr.addr.start",
                    "itr.traversed_len",
                ],
                "writes": [
                    "itr.curr.addr.start through kv",
                    "itr.traversed_len",
                    "fixture-only external-call observations",
                ],
                "external_state": ["scripted get_next_kv_addr fixture stimulus only"],
                "alias_sensitive": True,
            },
        },
    }


def effects() -> list[dict[str, str]]:
    values = [
        ("test-zero-start", "itr.curr", "read", "kv->addr.start == 0", 1868),
        (
            "initialize-sector-address",
            "itr.curr",
            "write",
            "kv->addr.start = sector.addr + SECTOR_HDR_DATA_SIZE",
            1869,
        ),
        (
            "call-and-assign-next-address",
            "db, sector, itr.curr",
            "call",
            "kv->addr.start = get_next_kv_addr(db, &sector, kv)",
            1870,
        ),
        ("compare-failed-address", "itr.curr", "read", "kv->addr.start == FAILED_ADDR", 1870),
        ("reset-kv-address", "itr.curr", "write", "kv->addr.start = 0", 1871),
        (
            "update-traversed-length",
            "itr",
            "read_write",
            "itr->traversed_len += db_sec_size(db)",
            1872,
        ),
        ("continue-current-loop", "itr", "compute", "continue", 1873),
    ]
    return [
        {
            "id": effect_id,
            "pointer_node": pointer,
            "kind": kind,
            "expression": expression,
            "source": f"src/fdb_kvdb.c:{line}",
        }
        for effect_id, pointer, kind, expression, line in values
    ]


def edges() -> list[dict[str, str]]:
    values = [
        ("test-zero-start", "initialize-sector-address", "control_depends"),
        ("test-zero-start", "call-and-assign-next-address", "control_depends"),
        ("call-and-assign-next-address", "compare-failed-address", "data_influences"),
        ("compare-failed-address", "reset-kv-address", "control_depends"),
        ("reset-kv-address", "update-traversed-length", "control_depends"),
        ("update-traversed-length", "continue-current-loop", "control_depends"),
    ]
    return [
        {"from_effect": source, "to_effect": target, "relationship": relationship}
        for source, target, relationship in values
    ]
