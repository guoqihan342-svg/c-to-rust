from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256
from .build_ir_toolchains import MAX_TRANSLATION_UNITS, tool_basename
from .c_compilation_fact_validation_receipt import (
    valid_reason_code, validate_compilation_receipt,
)
from .c_compilation_fact_validation_runtime import (
    validate_compilation_runtime,
)
from .host_tool_binding import classify_tool_basename


_KIND = "c-compilation-fact-bundle-v1"
_PROFILES = {"competition", "development"}


def validate_c_compilation_fact_bundle(value: Any) -> dict[str, Any]:
    fields = {
        "schema_version", "artifact_kind", "status", "profile",
        "build_ir_semantic_sha256", "sandbox", "toolchains", "units",
        "summary", "claim_boundary", "bundle_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c_compilation_fact_bundle_fields_invalid")
    bundle = dict(value)
    core = {key: bundle[key] for key in fields - {"bundle_sha256"}}
    if (
        bundle.get("schema_version") != 1
        or bundle.get("artifact_kind") != _KIND
        or bundle.get("profile") not in _PROFILES
        or not is_sha256(bundle.get("build_ir_semantic_sha256"))
        or bundle.get("bundle_sha256") != content_sha256(core)
        or bundle.get("claim_boundary") != {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "scope": "compiler_syntax_witness_only",
        }
    ):
        raise ValueError("c_compilation_fact_bundle_invalid")
    units = bundle.get("units")
    summary = bundle.get("summary")
    if (
        not isinstance(units, list)
        or not isinstance(summary, Mapping)
        or set(summary) != {
            "total", "observed", "passed", "blocked", "unavailable_reason",
        }
    ):
        raise ValueError("c_compilation_fact_bundle_invalid")
    if units:
        toolchains, probe_sha256 = validate_compilation_runtime(
            bundle.get("sandbox"), bundle.get("toolchains"),
        )
        checked = [
            validate_compilation_receipt(item, toolchains, probe_sha256)
            for item in units
        ]
    else:
        if bundle.get("sandbox") is not None or bundle.get("toolchains") != []:
            raise ValueError("c_compilation_fact_bundle_unavailable_invalid")
        toolchains, checked = {}, []
    ids = [item["unit_id"] for item in checked]
    passed = sum(item["status"] == "syntax_passed" for item in checked)
    blocked = len(checked) - passed
    expected_status = (
        "unavailable" if not checked
        else "ready" if blocked == 0
        else "ready_with_boundaries"
    )
    total = summary.get("total")
    unavailable_reason = summary.get("unavailable_reason")
    if (
        ids != sorted(ids)
        or len(ids) != len(set(ids))
        or bundle.get("status") != expected_status
        or type(total) is not int
        or not 0 < total <= MAX_TRANSLATION_UNITS
        or (checked and total != len(checked))
        or summary != {
            "total": total, "observed": len(checked), "passed": passed,
            "blocked": blocked, "unavailable_reason": unavailable_reason,
        }
        or (not checked) != valid_reason_code(unavailable_reason)
        or checked and unavailable_reason is not None
        or checked and set(toolchains) != {
            item["toolchain_id"] for item in checked
        }
    ):
        raise ValueError("c_compilation_fact_bundle_summary_invalid")
    return bundle


def compiler_facts_for_index(
    value: Mapping[str, Any],
    translation_units: Sequence[Mapping[str, Any]],
    *,
    build_ir_semantic_sha256: str,
) -> dict[str, dict[str, Any]]:
    bundle = validate_c_compilation_fact_bundle(value)
    if bundle["build_ir_semantic_sha256"] != build_ir_semantic_sha256:
        raise ValueError("c_compilation_fact_build_ir_drifted")
    expected = {}
    for unit in translation_units:
        if not isinstance(unit, Mapping):
            raise ValueError("c_compilation_fact_translation_unit_invalid")
        unit_id = unit.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id or unit_id in expected:
            raise ValueError("c_compilation_fact_translation_unit_invalid")
        expected[unit_id] = unit
    if bundle["summary"]["total"] != len(expected):
        raise ValueError("c_compilation_fact_translation_unit_drifted")
    if bundle["status"] == "unavailable":
        return {}
    if {item["unit_id"] for item in bundle["units"]} != set(expected):
        raise ValueError("c_compilation_fact_translation_unit_drifted")
    toolchains = {
        item["toolchain_id"]: item for item in bundle["toolchains"]
    }
    result: dict[str, dict[str, Any]] = {}
    for receipt in bundle["units"]:
        unit = expected.get(receipt["unit_id"])
        source = unit.get("source") if isinstance(unit, Mapping) else None
        compile_arguments = (
            unit.get("compile_arguments") if isinstance(unit, Mapping) else None
        )
        expanded_argv_sha256 = unit.get("expanded_argv_sha256")
        if expanded_argv_sha256 is None and isinstance(compile_arguments, Mapping):
            expanded_argv_sha256 = compile_arguments.get("expanded_argv_sha256")
        toolchain = toolchains[receipt["toolchain_id"]]
        try:
            compiler_family, _ = classify_tool_basename(
                tool_basename(unit.get("compiler")),
            )
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "c_compilation_fact_translation_unit_drifted"
            ) from error
        if (
            not isinstance(source, Mapping)
            or source.get("sha256") != receipt["source_sha256"]
            or expanded_argv_sha256 != receipt["expanded_argv_sha256"]
            or unit.get("toolchain_id") != receipt["toolchain_id"]
            or compiler_family != toolchain["family"]
        ):
            raise ValueError("c_compilation_fact_translation_unit_drifted")
        result[receipt["unit_id"]] = _index_fact(receipt, toolchain)
    return result


def _index_fact(
    receipt: Mapping[str, Any], toolchain: Mapping[str, Any],
) -> dict[str, Any]:
    keys = (
        "unit_id", "status", "reason_code", "source_sha256",
        "expanded_argv_sha256", "toolchain_id", "toolchain_binding_sha256",
        "compile_context_sha256", "plan_sha256", "receipt_sha256",
        "command_started", "diagnostics_sha256", "diagnostic_bytes",
    )
    return {
        **{key: receipt[key] for key in keys},
        "compiler_basename": toolchain["basename"],
        "compiler_binary_sha256": toolchain["binary"]["sha256"],
        "compiler_binary_size_bytes": toolchain["binary"]["size_bytes"],
        "syntax_passed": receipt["status"] == "syntax_passed",
        "evidence_scope": "exact_original_compiler_syntax_only",
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


__all__ = [
    "compiler_facts_for_index",
    "validate_c_compilation_fact_bundle",
]
