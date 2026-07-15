from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .rust_candidate_facts import derive_rust_metadata
from .rust_project_ir_source_facts import (
    derive_bound_candidate_source_facts, project_bound_public_items,
)
from .rust_project_ir_topology import derive_project_interface_plan
from .rust_project_ir_validation import RustProjectIRError


def recompute_bound_interface_plan(
    value: Mapping[str, Any], dag: Mapping[str, Any],
    build_irs: list[Mapping[str, Any]], candidate_sources: Mapping[str, bytes],
    *, compilation_facts_complete: bool,
) -> dict[str, Any]:
    _require_host_derived_empty_sections(value)
    modules = {str(item["unit_id"]): item for item in value["modules"]}
    public_by_module: dict[str, list[tuple[str, str, str]]] = {}
    for record in value["public_api"]:
        if record["visibility"] != "public":
            _fail("RustProjectIR derived public interface visibility drifted")
        public_by_module.setdefault(str(record["module_id"]), []).append((
            str(record["symbol"]), str(record["kind"]), str(record["signature"]),
        ))
    candidates = []
    for unit_id in dag["dag_order"]:
        module = modules[str(unit_id)]
        try:
            source = candidate_sources[str(unit_id)].decode("utf-8")
        except UnicodeError as error:
            raise RustProjectIRError("bound Rust candidate is not UTF-8") from error
        metadata = derive_rust_metadata(source)
        facts = derive_bound_candidate_source_facts(
            source, metadata["public_symbols"],
        )
        expected = sorted(
            (str(item["symbol"]), str(item["kind"]), str(item["signature"]))
            for item in project_bound_public_items(
                metadata["public_symbols"], facts,
            )
        )
        actual = sorted(public_by_module.get(str(module["module_id"]), []))
        if actual != expected:
            _fail("RustProjectIR public interface drifted from candidate source")
        candidates.append({
            "unit_id": str(unit_id),
            "candidate_sha256": str(module["candidate_sha256"]),
            "module_id": str(module["module_id"]),
            "source_facts": facts,
        })
    plan = derive_project_interface_plan(
        build_irs=build_irs, candidates=candidates,
        dependencies={str(key): list(items) for key, items in dag["dag"].items()},
        native_link_requirements=value["native_link_requirements"],
        compilation_facts_complete=compilation_facts_complete,
    )
    crate = value["crate"]
    if (
        crate["crate_id"] != plan["crate_id"]
        or crate["crate_types"] != plan["crate_types"]
        or crate["targets"] != plan["targets"]
        or value["interface_completeness"] != plan["interface_completeness"]
    ):
        _fail("RustProjectIR derived interface facts drifted")
    return plan


def _require_host_derived_empty_sections(value: Mapping[str, Any]) -> None:
    completeness = value["interface_completeness"]
    verified = set(completeness["verified_sections"])
    sections = {
        "cfg-feature-extraction": ("cfgs", "features"),
        "global-ownership": ("global_ownership",),
        "initialization-destruction": ("initialization",),
        "shared-type-layout": ("shared_types",),
    }
    for fact, records in sections.items():
        if fact in verified and any(value[name] for name in records):
            _fail("RustProjectIR contains unbound derived interface records")
    if "nested-module-multi-target" in verified and any(
        item["parent_module_id"] is not None for item in value["modules"]
    ):
        _fail("RustProjectIR contains unbound nested module records")


def _fail(message: str) -> None:
    raise RustProjectIRError(message)


__all__ = ["recompute_bound_interface_plan"]
