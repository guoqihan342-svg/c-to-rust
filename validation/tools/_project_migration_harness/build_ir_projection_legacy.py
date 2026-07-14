from __future__ import annotations

from typing import Any


ABI_PREFIXES = ("-m", "-target", "--target", "--sysroot", "-isysroot", "/arch:")


def legacy_toolchains(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = {unit["toolchain_id"]: {
        "toolchain_id": unit["toolchain_id"],
        "driver": unit["compiler"],
        "wrappers": unit["compiler_wrappers"],
        "language": unit["language"],
        "identity": "compile-database-driver-token",
        "provenance": {"raw_fact_role": "discovery"},
    } for unit in units}
    return [result[key] for key in sorted(result)]


def abi_facts(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for unit in units:
        flags = [
            item for item in unit["compile_arguments"]["semantic_flags"]
            if item.startswith(ABI_PREFIXES)
        ]
        result.append({
            "unit_id": unit["unit_id"],
            "language": unit["language"],
            "toolchain_id": unit["toolchain_id"],
            "target_flags": flags,
            "data_model": "explicit-flags" if flags else "compiler-default",
            "provenance": {"raw_fact_role": "discovery"},
        })
    return result


__all__ = ["ABI_PREFIXES", "abi_facts", "legacy_toolchains"]
