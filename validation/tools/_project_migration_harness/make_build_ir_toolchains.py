from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .build_ir import stable_build_id
from .build_ir_projection_legacy import ABI_PREFIXES


def legacy_toolchain_id(tool: str, report: Mapping[str, Any]) -> str:
    return stable_build_id("toolchain", {
        "tool": tool,
        "evidence_sha256": report["toolchain_ref"]["sha256"],
    })


def legacy_toolchains(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    tools = sorted({command["tool"] for command in report["commands"]})
    result = [{
        "toolchain_id": legacy_toolchain_id(tool, report),
        "driver": tool,
        "wrappers": [],
        "language": "c" if "c" in tool else "build",
        "identity": "hash-bound-make-toolchain-evidence",
        "evidence_sha256": report["toolchain_ref"]["sha256"],
        "provenance": {"raw_fact_role": "make-dry-run-report"},
    } for tool in tools]
    return sorted(result, key=lambda item: item["toolchain_id"])


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
            "provenance": {"raw_fact_role": "make-dry-run-report"},
        })
    return result


__all__ = ["abi_facts", "legacy_toolchain_id", "legacy_toolchains"]
