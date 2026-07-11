from typing import Any

from .constants import FUNCTION_NAME


def build_c_boundary(source_file: str, source_hash: str) -> dict[str, Any]:
    return {
        "oracle_source_mode": "embedded_slice_c_source",
        "files": [{"path": source_file, "role": "source", "sha256": source_hash}],
        "functions": [FUNCTION_NAME],
        "signatures": [carrier_signature(), external_signature()],
        "direct_dependencies": dependencies(source_file),
        "pointer_contract": pointer_contract(),
        "external_direct_callees": [
            {
                "name": "get_next_kv_addr",
                "signature_ref": "sig-scripted-next",
                "source_ref": "translation-carrier:scripted-get-next-kv-addr",
                "source_files": [{"path": source_file, "sha256": source_hash}],
                "definition_status": "deterministic_fixture_stimulus",
                "stub_boundary": "scripted_fixture_only_no_real_callee_semantics",
            }
        ],
    }


def carrier_signature() -> dict[str, Any]:
    return {
        "id": "sig-carrier",
        "function": FUNCTION_NAME,
        "return_type": "bool",
        "parameters": [
            {"name": "db", "c_type": "struct Database *", "direction": "inout"},
            {"name": "sector_seed", "c_type": "struct Sector", "direction": "input"},
            {"name": "SECTOR_HDR_DATA_SIZE", "c_type": "uint32_t", "direction": "input"},
            {"name": "itr", "c_type": "struct Owner *", "direction": "inout"},
        ],
        "definition_status": "synthetic_translation_carrier",
    }


def external_signature() -> dict[str, Any]:
    return {
        "id": "sig-scripted-next",
        "function": "get_next_kv_addr",
        "return_type": "uint32_t",
        "parameters": [
            {"name": "db", "c_type": "struct Database *", "direction": "inout"},
            {"name": "sector", "c_type": "struct Sector *", "direction": "inout"},
            {"name": "kv", "c_type": "struct Kv *", "direction": "inout"},
        ],
        "definition_status": "deterministic_fixture_stimulus",
    }


def dependencies(source_file: str) -> list[dict[str, str]]:
    return [
        {"kind": "macro", "name": "SECTOR_HDR_DATA_SIZE", "source": source_file, "definition_status": "fixture_bound_same_name_u32_parameter"},
        {"kind": "macro", "name": "FAILED_ADDR", "source": source_file, "definition_status": "carrier_equivalent_uint32_sentinel"},
        {"kind": "macro", "name": "db_sec_size", "source": f"{source_file}:86", "definition_status": "carrier_equivalent_direct_u32_field_read"},
        {"kind": "callee", "name": "get_next_kv_addr", "source": f"{source_file}#get_next_kv_addr", "definition_status": "deterministic_fixture_stimulus_only"},
    ]


def pointer_contract() -> dict[str, Any]:
    return {
        "input_buffers": [],
        "output_pointers": [
            {"name": "db", "c_type": "struct Database *", "nullability": "non_null", "ownership_role": "inout_param", "mutability": "read_write"},
            {"name": "itr", "c_type": "struct Owner *", "nullability": "non_null", "ownership_role": "inout_param", "mutability": "read_write"},
        ],
        "aliasing_proven": True,
        "noalias_required": [["db", "itr"]],
    }
