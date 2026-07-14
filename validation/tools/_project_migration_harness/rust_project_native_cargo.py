from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any


def native_link_build_script(ir: Mapping[str, Any]) -> bytes | None:
    requirements = ir["native_link_requirements"]
    plans = ir["native_link_plans"]
    if not requirements:
        if plans:
            raise ValueError("rust_project_ir_native_link_plan_without_requirement")
        return None
    if not plans:
        raise ValueError("rust_project_ir_native_link_plan_missing")
    if any(item["strategy"] != "rustc-link-lib" for item in plans):
        raise ValueError("rust_project_ir_native_link_strategy_unmaterialized")
    lines = [
        "// Candidate directives; host resolution evidence is still required.",
        "fn main() {",
        '    println!("cargo:rerun-if-changed=migration-rust-project-ir.json");',
    ]
    for plan in plans:
        lines.append(
            '    println!("cargo:rustc-link-lib='
            f'{plan["rustc_link_kind"]}={plan["rustc_link_name"]}");'
        )
    lines.extend(("}", ""))
    return "\n".join(lines).encode("ascii")


def native_link_generation_binding(
    ir: Mapping[str, Any], build_script: bytes | None,
) -> dict[str, Any]:
    if build_script is None:
        return {
            "status": "not-required", "requirement_count": 0,
            "candidate_sha256": None, "build_script_sha256": None,
            "resolution_gate": False,
        }
    candidate_sha256s = {
        str(item["candidate_sha256"]) for item in ir["native_link_plans"]
    }
    if len(candidate_sha256s) != 1:
        raise ValueError("rust_project_ir_native_link_candidate_cohort_invalid")
    return {
        "status": "candidate-materialized",
        "requirement_count": len(ir["native_link_requirements"]),
        "candidate_sha256": next(iter(candidate_sha256s)),
        "build_script_sha256": hashlib.sha256(build_script).hexdigest(),
        "resolution_gate": False,
    }


__all__ = ["native_link_build_script", "native_link_generation_binding"]
