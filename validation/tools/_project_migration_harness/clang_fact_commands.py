from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256
from .build_ir_projection_legacy import ABI_PREFIXES
from .build_ir_toolchains import tool_basename
from .build_ir_validation import validate_build_ir
from .clang_interface_fact_evidence import MAX_AST_BYTES
from .clang_record_layout_fact_evidence import MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES
from .clang_fact_command_security import (
    compatible_clang_targets,
    rebuild_clang_compile_context,
    safe_clang_text,
)


CLANG_FACT_PLAN_KIND = "project-migration-clang-fact-plan"
CLANG_TOOLCHAIN_BINDING_KIND = "clang-toolchain-portable-binding"
MAX_CLANG_DIAGNOSTIC_BYTES = 2 * 1024 * 1024
_GATES = {
    "clang-ast": ("-ast-dump=json", MAX_AST_BYTES,
                  MAX_AST_BYTES + MAX_CLANG_DIAGNOSTIC_BYTES),
    "clang-record-layout": ("-fdump-record-layouts-complete",
                            MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES,
                            MAX_CLANG_RECORD_LAYOUT_EVIDENCE_BYTES),
}
_PLAN_FIELDS = {
    "schema_version", "artifact_kind", "status", "gate", "unit_id", "source",
    "working_directory", "build_ir_sha256", "build_ir_semantic_sha256",
    "toolchain", "toolchain_portable_sha256", "target_context",
    "target_context_sha256", "compile_context", "compile_context_sha256",
    "argv", "argv_sha256", "input_sha256", "max_stdout_bytes",
    "max_stderr_bytes", "max_combined_bytes", "semantic_gate",
    "translation_coverage_numerator", "plan_sha256",
}
_BINDING_FIELDS = {"schema_version", "artifact_kind", "status", "family",
                   "basename", "binary", "version", "target", "resource_dir",
                   "sysroot", "binding_sha256"}
_VALUE_PROBE = {"status", "value", "stdout_sha256", "stderr_sha256"}
_PATH_PROBE = {"status", "stdout_sha256", "stderr_sha256"}


def build_clang_fact_plans(build_ir: Mapping[str, Any],
                           clang_toolchain_binding: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_build_ir(build_ir)
    toolchain = _clang_toolchain(clang_toolchain_binding)
    return [_plan(build_ir, unit, gate, toolchain)
            for unit in build_ir["translation_units"] for gate in _GATES]


def validate_clang_fact_plan(plan: Mapping[str, Any], build_ir: Mapping[str, Any],
                             clang_toolchain_binding: Mapping[str, Any]) -> dict[str, Any]:
    validate_build_ir(build_ir)
    if not isinstance(plan, Mapping) or set(plan) != _PLAN_FIELDS:
        raise ValueError("clang_fact_plan_fields_invalid")
    core = {key: plan[key] for key in _PLAN_FIELDS - {"plan_sha256"}}
    if plan.get("plan_sha256") != content_sha256(core):
        raise ValueError("clang_fact_plan_sha256_invalid")
    if plan.get("argv_sha256") != content_sha256(plan.get("argv")):
        raise ValueError("clang_fact_plan_argv_sha256_invalid")
    units = [item for item in build_ir["translation_units"]
             if item["unit_id"] == plan.get("unit_id")]
    if len(units) != 1 or plan.get("gate") not in _GATES:
        raise ValueError("clang_fact_plan_identity_invalid")
    expected = _plan(build_ir, units[0], str(plan["gate"]),
                     _clang_toolchain(clang_toolchain_binding))
    if dict(plan) != expected:
        raise ValueError("clang_fact_plan_drifted")
    return dict(plan)


def _plan(build_ir: Mapping[str, Any], unit: Mapping[str, Any], gate: str,
          toolchain: dict[str, Any]) -> dict[str, Any]:
    source = unit["source"]
    rebuilt = rebuild_clang_compile_context(unit)
    source_path = rebuilt["source_path"]
    working = rebuilt["working_directory"]
    semantic = rebuilt["semantic_arguments"]
    compile_context = {"language": unit["language"], "semantic_arguments": semantic,
                       "includes": rebuilt["includes"], "defines": rebuilt["defines"]}
    target_context = _target_context(
        build_ir, unit, toolchain, rebuilt["explicit_targets"], semantic,
    )
    source_id = {"path": source_path, "sha256": source["sha256"],
                 "size_bytes": source["size_bytes"]}
    flag, stdout_limit, combined_limit = _GATES[gate]
    fixed = [
        f"--target={toolchain['target']['value']}",
        "-resource-dir", "/toolchain/resource",
    ]
    if toolchain["sysroot"]["status"] == "reported":
        fixed.append("--sysroot=/toolchain/sysroot")
    argv = [
        "clang", "--no-default-config", *fixed, *rebuilt["argv"],
        "-fsyntax-only", "-Xclang", flag, "--", source_path,
    ]
    build_sha, tool_sha = content_sha256(dict(build_ir)), content_sha256(toolchain)
    target_sha, compile_sha, argv_sha = map(content_sha256,
                                                (target_context, compile_context, argv))
    bindings = {
        "gate": gate, "unit_id": unit["unit_id"], "source": source_id,
        "working_directory": working, "build_ir_sha256": build_sha,
        "build_ir_semantic_sha256": build_ir["semantic_sha256"],
        "toolchain_portable_sha256": tool_sha, "target_context_sha256": target_sha,
        "compile_context_sha256": compile_sha, "argv_sha256": argv_sha,
        "max_stdout_bytes": stdout_limit, "max_stderr_bytes": MAX_CLANG_DIAGNOSTIC_BYTES,
        "max_combined_bytes": combined_limit,
    }
    core = {
        "schema_version": 1, "artifact_kind": CLANG_FACT_PLAN_KIND, "status": "ready",
        "gate": gate, "unit_id": unit["unit_id"], "source": source_id,
        "working_directory": working, "build_ir_sha256": build_sha,
        "build_ir_semantic_sha256": build_ir["semantic_sha256"],
        "toolchain": toolchain, "toolchain_portable_sha256": tool_sha,
        "target_context": target_context, "target_context_sha256": target_sha,
        "compile_context": compile_context, "compile_context_sha256": compile_sha,
        "argv": argv, "argv_sha256": argv_sha, "input_sha256": content_sha256(bindings),
        "max_stdout_bytes": stdout_limit, "max_stderr_bytes": MAX_CLANG_DIAGNOSTIC_BYTES,
        "max_combined_bytes": combined_limit, "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return {**core, "plan_sha256": content_sha256(core)}


def _clang_toolchain(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise ValueError("clang_toolchain_binding_fields_invalid")
    core = {key: value[key] for key in _BINDING_FIELDS - {"binding_sha256"}}
    binary = value.get("binary")
    if (value.get("schema_version") != 1
            or value.get("artifact_kind") != CLANG_TOOLCHAIN_BINDING_KIND
            or value.get("status") != "ready" or value.get("family") != "clang-compiler"
            or re.fullmatch(r"clang(?:-[0-9]+(?:\.[0-9]+)*)?",
                            str(value.get("basename"))) is None
            or not isinstance(binary, Mapping) or set(binary) != {"sha256", "size_bytes"}
            or not is_sha256(binary.get("sha256")) or type(binary.get("size_bytes")) is not int
            or binary["size_bytes"] <= 0 or value.get("binding_sha256") != content_sha256(core)):
        raise ValueError("clang_toolchain_binding_invalid")
    version, target = _value_probe(value.get("version"), "version"), _value_probe(
        value.get("target"), "target")
    if re.search(r"\bclang version [0-9]", version["value"], re.I) is None:
        raise ValueError("clang_toolchain_version_invalid")
    compatible_clang_targets(target["value"], target["value"])
    _path_probe(value.get("resource_dir"), "resource_dir", {"reported"})
    _path_probe(value.get("sysroot"), "sysroot",
                {"reported", "reported-empty/default", "not-applicable"})
    return core


def _target_context(build_ir: Mapping[str, Any], unit: Mapping[str, Any],
                    clang: Mapping[str, Any], explicit: list[str],
                    semantic: list[str]) -> dict[str, Any]:
    records = [item for item in build_ir["toolchains"]
               if item["toolchain_id"] == unit["toolchain_id"]]
    if len(records) != 1 or build_ir["claim_boundary"].get("host_toolchain_bound") is not True:
        raise ValueError("clang_fact_build_ir_host_target_missing")
    record = records[0]
    drivers = [item for item in record.get("tools", []) if item.get("relation") == "driver"]
    if (record.get("role") != "compiler-driver" or record.get("wrappers") != []
            or len(drivers) != 1 or "compiler-driver" not in drivers[0].get("roles", [])
            or tool_basename(str(record.get("driver"))) != tool_basename(str(unit.get("compiler")))
            or record.get("language") != unit.get("language")):
        raise ValueError("clang_fact_build_ir_toolchain_invalid")
    probe = drivers[0].get("target")
    if not isinstance(probe, Mapping) or probe.get("status") != "reported":
        raise ValueError("clang_fact_build_ir_host_target_missing")
    host, clang_target = str(probe.get("value")), str(clang["target"]["value"])
    if not compatible_clang_targets(host, clang_target):
        raise ValueError("clang_fact_target_incompatible")
    if any(not (
        compatible_clang_targets(host, item)
        and compatible_clang_targets(clang_target, item)
    ) for item in explicit):
        raise ValueError("clang_fact_target_drifted")
    abi = [item for item in build_ir["abi_facts"] if item["unit_id"] == unit["unit_id"]]
    flags = [item for item in semantic if item.startswith(ABI_PREFIXES)]
    if len(abi) != 1 or abi[0].get("target_flags") != flags:
        raise ValueError("clang_fact_abi_target_drifted")
    return {"build_ir_host_target": host, "clang_target": clang_target,
            "explicit_targets": explicit, "abi_target_flags": flags,
            "compatibility": "compatible"}


def _value_probe(value: Any, name: str) -> dict[str, str]:
    if (not isinstance(value, Mapping) or set(value) != _VALUE_PROBE
            or value.get("status") != "reported"
            or not all(is_sha256(value.get(key)) for key in ("stdout_sha256", "stderr_sha256"))):
        raise ValueError(f"clang_toolchain_{name}_probe_invalid")
    safe_clang_text(value.get("value"), f"clang_toolchain_{name}_value_invalid")
    return dict(value)


def _path_probe(value: Any, name: str, statuses: set[str]) -> None:
    if (not isinstance(value, Mapping) or set(value) != _PATH_PROBE
            or value.get("status") not in statuses
            or not all(is_sha256(value.get(key)) for key in ("stdout_sha256", "stderr_sha256"))):
        raise ValueError(f"clang_toolchain_{name}_probe_invalid")


__all__ = ["CLANG_FACT_PLAN_KIND", "CLANG_TOOLCHAIN_BINDING_KIND",
           "MAX_CLANG_DIAGNOSTIC_BYTES", "build_clang_fact_plans",
           "validate_clang_fact_plan"]
