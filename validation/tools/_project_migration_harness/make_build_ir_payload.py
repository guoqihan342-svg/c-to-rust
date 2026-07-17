from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any

from .build_ir import (
    BUILD_IR_KIND, finalize_build_ir, normalize_binding,
)
from .build_ir_link_authority import link_authority_claim, schema_for_extractor
from .build_ir_projection import target_closure
from .make_build_ir_toolchains import abi_facts


def assemble_make_build_ir(
    report: Mapping[str, Any], report_reference: Mapping[str, Any],
    units: list[dict[str, Any]], targets: list[dict[str, Any]],
    external: list[dict[str, Any]], toolchains: list[dict[str, Any]],
    closure: Mapping[str, Any], extractor: Mapping[str, str], *,
    toolchain_reference: Mapping[str, Any] | None,
    host_toolchain_bound: bool, toolchain_profile: str | None,
) -> dict[str, Any]:
    sources = _unique_bindings([unit["source"] for unit in units])
    raw_refs = [{"role": "make-dry-run-report", **dict(report_reference)}]
    if toolchain_reference is not None:
        raw_refs.append({
            "role": "c-toolchain-evidence", **dict(toolchain_reference),
        })
    payload = {
        "schema_version": schema_for_extractor(extractor),
        "artifact_kind": BUILD_IR_KIND,
        "status": "ready_with_boundaries",
        "extractor": dict(extractor),
        "raw_fact_refs": sorted(raw_refs, key=lambda item: item["role"]),
        "build_metadata": [
            normalize_binding(report["makefile_ref"], materialized=True)
        ],
        "translation_units": units,
        "source_inputs": sources,
        "generated_inputs": closure["generated_inputs"],
        "targets": targets,
        "target_closure": target_closure(targets),
        "toolchains": toolchains,
        "external_dependencies": external,
        "abi_facts": abi_facts(units),
        "boundaries": closure["boundaries"],
        "claim_boundary": {
            **closure["claim_boundary"],
            "host_toolchain_bound": host_toolchain_bound,
            "toolchain_profile": toolchain_profile,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            **link_authority_claim(extractor, targets, units),
        },
    }
    return finalize_build_ir(payload)


def _unique_bindings(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {item["path"]: copy.deepcopy(item) for item in values}
    if len(keyed) != len(values):
        raise ValueError("make_build_ir_source_binding_duplicate")
    return [keyed[path] for path in sorted(keyed)]


__all__ = ["assemble_make_build_ir"]
