from __future__ import annotations

from collections.abc import Mapping
import copy
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256


BUILD_IR_SCHEMA_VERSION = 1
BUILD_IR_KIND = "c2r-canonical-build-ir"
BUILD_IR_EXTRACTOR = {
    "name": "project-migration-build-ir",
    "version": "1",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

def stable_build_id(kind: str, value: Any) -> str:
    return f"{kind}-{content_sha256(value)[:24]}"


def normalize_binding(value: Any, *, materialized: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("path"), str):
        raise ValueError("build_ir_binding_invalid")
    result = {
        "path": value["path"],
        "kind": value.get("kind", "file"),
        "materialized": bool(materialized),
    }
    if materialized:
        result.update({
            "sha256": value.get("sha256"),
            "size_bytes": value.get("size_bytes"),
        })
        if result["kind"] == "directory":
            result["entry_count"] = value.get("entry_count")
    return result


def validate_artifact_reference(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(code)
    if not safe_posix_path(value.get("path")) or not is_sha256(value.get("sha256")):
        raise ValueError(code)
    size = value.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError(code)
    return value


def validate_materialized_binding(value: Mapping[str, Any], materialized: Any) -> None:
    if not isinstance(materialized, bool) or not safe_posix_path(value.get("path")):
        raise ValueError("build_ir_binding_invalid")
    if value.get("kind") not in {"file", "directory"}:
        raise ValueError("build_ir_binding_invalid")
    size = value.get("size_bytes")
    if materialized and (
        not is_sha256(value.get("sha256"))
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise ValueError("build_ir_binding_invalid")


def safe_posix_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    return (
        bool(posix.parts) and not posix.is_absolute() and not windows.drive and ".." not in posix.parts
        and not posix.parts[0].startswith("~") and posix.as_posix() == value
    )


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def target_record(
    identifier: str, name: str, kind: str, outputs: list[dict[str, Any]],
    inputs: list[dict[str, Any]], dependencies: list[str],
    argument_sets: list[dict[str, Any]], link_args: list[str],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "target_id": identifier,
        "name": name,
        "kind": kind,
        "outputs": outputs,
        "ordered_inputs": inputs,
        "dependency_target_ids": dependencies,
        "compile_argument_sets": argument_sets,
        "ordered_link_arguments": link_args,
        "provenance": provenance,
    }


def merge_meson_targets(
    closure: Mapping[str, Any],
    targets: list[dict[str, Any]],
    owners: dict[str, str],
    external: list[dict[str, Any]],
) -> None:
    generated = closure.get("generated_stage_facts")
    meson = generated.get("meson_introspection") if isinstance(generated, Mapping) else None
    if not isinstance(meson, Mapping) or meson.get("status") != "ready":
        return
    by_id = {item["target_id"]: item for item in targets}
    meson_ids: dict[str, str] = {}
    raw_targets = list_value(meson.get("targets"))
    for raw in raw_targets:
        outputs = [
            normalize_binding(value, materialized=value.get("materialized", True))
            for value in list_value(raw.get("outputs"))
        ]
        matches = {owners[item["path"]] for item in outputs if item["path"] in owners}
        if len(matches) > 1:
            raise ValueError("build_ir_meson_target_ambiguous")
        target_id = next(iter(matches), stable_build_id("target", {
            "kind": raw.get("type"),
            "outputs": [item["path"] for item in outputs],
            "fallback": raw.get("id"),
        }))
        meson_ids[str(raw.get("id"))] = target_id
        if target_id not in by_id:
            item = target_record(
                target_id, str(raw.get("name")), str(raw.get("type")), outputs,
                [], [], [], [], {
                    "raw_fact_role": "generated-build-closure",
                    "meson_target_id": raw.get("id"),
                },
            )
            targets.append(item)
            by_id[target_id] = item
            for output in outputs:
                if output["path"] in owners:
                    raise ValueError("build_ir_target_output_duplicate")
                owners[output["path"]] = target_id
        else:
            by_id[target_id]["kind"] = str(raw.get("type"))
            by_id[target_id]["provenance"]["meson_target_id"] = raw.get("id")
    for raw in raw_targets:
        target_id = meson_ids[str(raw.get("id"))]
        target = by_id[target_id]
        existing_inputs = {
            item["binding"]["path"] for item in target["ordered_inputs"]
        }
        for group in list_value(raw.get("source_groups")):
            target["compile_argument_sets"].append({
                key: copy.deepcopy(group[key])
                for key in (
                    "kind", "language", "machine", "compiler_summary",
                    "linker_summary", "parameters_summary",
                ) if key in group
            })
            for role, key in (("source", "sources"),
                              ("generated-source", "generated_sources")):
                for source in list_value(group.get(key)):
                    binding = normalize_binding(
                        source, materialized=source.get("materialized", True)
                    )
                    if binding["path"] in existing_inputs:
                        continue
                    dependency = owners.get(binding["path"])
                    if dependency == target_id:
                        dependency = None
                    target["ordered_inputs"].append({
                        "ordinal": len(target["ordered_inputs"]),
                        "role": role,
                        "binding": binding,
                        "dependency_target_id": dependency,
                    })
                    existing_inputs.add(binding["path"])
                    if dependency and dependency not in target["dependency_target_ids"]:
                        target["dependency_target_ids"].append(dependency)
        for dependency in string_list(raw.get("target_dependency_ids")):
            resolved = meson_ids.get(dependency)
            if resolved and resolved not in target["dependency_target_ids"]:
                target["dependency_target_ids"].append(resolved)
        for name in string_list(raw.get("external_dependency_names")):
            external.append({
                "dependency_id": stable_build_id(
                    "external", {"target": target_id, "name": name}
                ),
                "kind": "declared-external-dependency",
                "name": name,
                "consumer_target_ids": [target_id],
                "ordinal": None,
                "provenance": {"raw_fact_role": "generated-build-closure"},
            })


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: Any) -> list[str]:
    return [item for item in list_value(value) if isinstance(item, str)]


def semantic_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    included = {
        key: copy.deepcopy(item)
        for key, item in value.items()
        if key not in {
            "build_metadata",
            "claim_boundary",
            "extractor",
            "raw_fact_refs",
            "semantic_sha256",
        }
    }
    return _without_provenance(included)


def finalize_build_ir(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(payload))
    result["semantic_sha256"] = content_sha256(semantic_projection(result))
    return result


def canonical_build_ir_bytes(value: Mapping[str, Any]) -> bytes:
    if value.get("schema_version") != BUILD_IR_SCHEMA_VERSION:
        raise ValueError("build_ir_schema_version_invalid")
    if value.get("artifact_kind") != BUILD_IR_KIND:
        raise ValueError("build_ir_artifact_kind_invalid")
    if value.get("semantic_sha256") != content_sha256(semantic_projection(value)):
        raise ValueError("build_ir_semantic_sha256_invalid")
    return canonical_json_bytes(dict(value))


def translation_units_for_index(build_ir: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in build_ir.get("translation_units", []):
        if not isinstance(item, Mapping):
            raise ValueError("build_ir_translation_unit_invalid")
        arguments = item.get("compile_arguments")
        provenance = item.get("provenance")
        if not isinstance(arguments, Mapping) or not isinstance(provenance, Mapping):
            raise ValueError("build_ir_translation_unit_invalid")
        result.append({
            "unit_id": item["unit_id"],
            "variant_id": item["unit_id"],
            "variant_index": item["variant_index"],
            "variant_count": item["variant_count"],
            "source": dict(item["source"]),
            "working_directory": item["working_directory"],
            "compiler": item["compiler"],
            "compiler_wrappers": list(item["compiler_wrappers"]),
            "language": item["language"],
            "includes": copy.deepcopy(item["includes"]),
            "defines": copy.deepcopy(item["defines"]),
            "redacted_define_count": item["redacted_define_count"],
            "semantic_flags": list(arguments["semantic_flags"]),
            "output": item["output"]["path"],
            "expanded_argv_sha256": arguments["expanded_argv_sha256"],
            "response_files": copy.deepcopy(arguments["response_files"]),
            "entry": {
                "index": provenance["entry_index"],
                "sha256": provenance["entry_sha256"],
            },
            "entry_sha256": provenance["entry_sha256"],
        })
    return result


def _without_provenance(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _without_provenance(item)
            for key, item in value.items()
            if key != "provenance"
        }
    if isinstance(value, list):
        return [_without_provenance(item) for item in value]
    return value


__all__ = [
    "BUILD_IR_EXTRACTOR",
    "BUILD_IR_KIND",
    "BUILD_IR_SCHEMA_VERSION",
    "canonical_build_ir_bytes",
    "finalize_build_ir",
    "list_value",
    "merge_meson_targets",
    "normalize_binding",
    "is_sha256",
    "safe_posix_path",
    "semantic_projection",
    "stable_build_id",
    "string_list",
    "target_record",
    "translation_units_for_index",
    "validate_artifact_reference",
    "validate_materialized_binding",
]
