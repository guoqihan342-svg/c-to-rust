from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json_artifact
from .build_ir_projection import project_build_ir
from .build_ir_toolchain_stage import (
    blocked_c_toolchain_stage, materialize_c_toolchain_stage,
)
from .build_ir_tool_selections import bound_standard_tool_requests
from .build_ir_toolchains import merge_tool_requests, standard_tool_requests
from .generated_closure import verify_generated_build_closure


def materialize_generated_build_ir_stage(
    repo_root: Path,
    output: Path,
    discovery: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    profile: str = "development",
) -> dict[str, Any]:
    from .build_ir_validation import verify_build_ir_artifact

    closure = discovery.get("generated_build_closure", {})
    artifacts["generated_build_closure"] = write_json_artifact(
        output, "plan/generated-build-closure.json", closure,
    )
    closure_verification = verify_generated_build_closure(repo_root, closure)
    artifacts["generated_build_closure_verification"] = write_json_artifact(
        output,
        "plan/generated-build-closure-verification.json",
        closure_verification,
    )
    requests = (
        bound_standard_tool_requests(repo_root, discovery, closure)
        if profile == "competition"
        else standard_tool_requests(discovery, closure)
    )
    toolchain_evidence = materialize_c_toolchain_stage(
        output,
        artifacts,
        merge_tool_requests(requests),
        profile=profile,
    )
    if toolchain_evidence is not None and toolchain_evidence.get("status") != "ready":
        return blocked_c_toolchain_stage(
            output,
            artifacts,
            toolchain_evidence,
            closure=closure,
            closure_verification=closure_verification,
        )
    raw_refs = [
        {"role": role, **artifacts[key]}
        for role, key in (
            ("discovery", "discovery"),
            ("generated-build-closure", "generated_build_closure"),
            (
                "generated-build-closure-verification",
                "generated_build_closure_verification",
            ),
        )
    ]
    if toolchain_evidence is not None:
        raw_refs.append({
            "role": toolchain_evidence["raw_fact_role"],
            **artifacts["c_toolchain_evidence"],
        })
    build_ir = project_build_ir(
        discovery,
        closure,
        closure_verification,
        raw_refs,
        toolchain_evidence,
    )
    artifacts["build_ir"] = write_json_artifact(
        output, "plan/build-ir.json", build_ir,
    )
    verification = verify_build_ir_artifact(
        repo_root, output, artifacts["build_ir"],
    )
    artifacts["build_ir_verification"] = write_json_artifact(
        output, "plan/build-ir-verification.json", verification,
    )
    return {
        "build_ir": build_ir,
        "closure": closure,
        "closure_verification": closure_verification,
        "closure_ready": (
            closure.get("status") == "ready"
            and closure_verification.get("status") == "verified"
        ),
        "verification": verification,
    }


__all__ = ["materialize_generated_build_ir_stage"]
