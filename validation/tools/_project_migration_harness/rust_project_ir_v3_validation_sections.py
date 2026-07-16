from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .rust_project_cargo_v3_link_semantics import occurrence_module_order
from .rust_project_ir_v3_topology_products import input_occurrence_id
from .rust_project_ir_validation import (
    RustProjectIRError, _FIELDS as _V2_FIELDS, _evidence, _record_shape, _sha,
    _string_list, _text,
)

_WORKSPACE_KEYS = {"workspace_id", "resolver", "package_ids",
                   "default_package_ids", "evidence"}
_PACKAGE_KEYS = {
    "package_id", "name", "build_ir_target_id", "product_kind",
    "dependency_package_ids", "target_ids", "module_ids", "evidence"}
_TARGET_KEYS = {
    "target_id", "package_id", "name", "kind", "crate_types", "build_ir_target_id",
    "module_ids", "input_occurrences", "ordered_link_arguments", "evidence"}
_MODULE_KEYS = {
    "module_id", "package_id", "target_id", "target_namespace_id", "rust_path",
    "unit_id", "source_unit_ids", "candidate_sha256", "visibility", "evidence"}
_SECTION_IDS = {
    "public_api": "declaration_id", "shared_types": "declaration_id",
    "global_ownership": "declaration_id", "initialization": "init_id",
    "ffi_boundaries": "declaration_id", "cfgs": "cfg_id", "features": "feature_id",
    "unsafe_obligations": "obligation_id",
}


def module_id_for_target_candidate(
    target_namespace_id: str, unit_id: str, candidate_sha256: str,
    source_unit_ids: Sequence[str],
) -> str:
    _text(target_namespace_id, "target_namespace_id")
    _text(unit_id, "unit_id")
    _sha(candidate_sha256, "candidate_sha256")
    sources = list(source_unit_ids) if not isinstance(source_unit_ids, str) else source_unit_ids
    _string_list(sources, "source_unit_ids", nonempty=True)
    digest = content_sha256({
        "target_namespace_id": target_namespace_id, "unit_id": unit_id,
        "candidate_sha256": candidate_sha256, "source_unit_ids": sources,
    })
    return f"module-{digest[:24]}"

def validate_v3_sections(value: Mapping[str, Any],
                         candidates: Mapping[str, Mapping[str, Any]],
                         builds: set[str]) -> None:
    packages, targets, modules = _topology(value, candidates, builds)
    _interface_sections(value, modules, candidates, builds)
    _topology_state(value, packages, targets, modules)


def _topology(
    value: Mapping[str, Any], candidates: Mapping[str, Mapping[str, Any]],
    builds: set[str],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]],
           dict[str, Mapping[str, Any]]]:
    workspace = value.get("workspace")
    if not isinstance(workspace, Mapping) or set(workspace) != _WORKSPACE_KEYS:
        _fail("RustProjectIR v3 workspace schema is invalid")
    _text(workspace.get("workspace_id"), "workspace_id")
    _text(workspace.get("resolver"), "workspace resolver")
    _string_list(
        workspace.get("package_ids"), "workspace.package_ids",
        nonempty=value.get("topology_status") == "ready",
    )
    _string_list(workspace.get("default_package_ids"), "workspace.default_package_ids")
    workspace_evidence = _evidence_sets(workspace.get("evidence"), candidates, builds)
    packages = _indexed(value.get("packages"), "packages", "package_id", _PACKAGE_KEYS)
    for package in packages.values():
        for key in ("name", "build_ir_target_id"):
            _text(package.get(key), f"package.{key}")
        if package.get("product_kind") not in {
            "static-library", "shared-library", "executable",
        }:
            _fail("RustProjectIR v3 package product_kind is invalid")
        for key in ("dependency_package_ids", "target_ids", "module_ids"):
            _string_list(package.get(key), f"package.{key}")
        _evidence(package.get("evidence"), candidates, builds)
    targets = _indexed(value.get("targets"), "targets", "target_id", _TARGET_KEYS)
    for target in targets.values():
        for key in ("package_id", "name", "build_ir_target_id"):
            _text(target.get(key), f"target.{key}")
        if target.get("kind") not in {"lib", "cdylib", "bin"}:
            _fail("RustProjectIR v3 target kind is invalid")
        _string_list(target.get("crate_types"), "target.crate_types", nonempty=True)
        _string_list(target.get("module_ids"), "target.module_ids")
        _ordered_strings(target.get("ordered_link_arguments"), "ordered_link_arguments")
        _evidence(target.get("evidence"), candidates, builds)
        _occurrences(target)
    modules = _indexed(value.get("modules"), "modules", "module_id", _MODULE_KEYS)
    for module in modules.values():
        for key in ("package_id", "target_id", "target_namespace_id",
                    "unit_id", "visibility"):
            _text(module.get(key), f"module.{key}")
        checked_relative_path(module.get("rust_path"))
        _sha(module.get("candidate_sha256"), "module.candidate_sha256")
        _string_list(module.get("source_unit_ids"), "module.source_unit_ids", nonempty=True)
        candidate = candidates.get(str(module["unit_id"]))
        if candidate is None or candidate["source"]["sha256"] != module["candidate_sha256"]:
            _fail("RustProjectIR v3 module does not bind its candidate source")
        expected = module_id_for_target_candidate(
            str(module["target_namespace_id"]), str(module["unit_id"]),
            str(module["candidate_sha256"]), module["source_unit_ids"],
        )
        if module["module_id"] != expected:
            _fail("RustProjectIR v3 module identity is invalid")
        evidence = _evidence_sets(module.get("evidence"), candidates, builds)
        if module["unit_id"] not in evidence[0] or module["candidate_sha256"] not in evidence[1]:
            _fail("RustProjectIR v3 module evidence does not bind its candidate")
    _topology_closure(
        workspace, packages, targets, modules, candidates,
        status=value.get("topology_status"),
    )
    expected_evidence = (
        set(candidates), {item["source"]["sha256"] for item in candidates.values()}, builds,
    )
    if workspace_evidence != expected_evidence:
        _fail("RustProjectIR v3 workspace evidence does not bind the complete project")
    return packages, targets, modules


def _topology_closure(workspace: Mapping[str, Any], packages: Mapping[str, Mapping[str, Any]],
                      targets: Mapping[str, Mapping[str, Any]],
                      modules: Mapping[str, Mapping[str, Any]],
                      candidates: Mapping[str, Any], *, status: Any) -> None:
    package_ids, target_ids = set(packages), set(targets)
    if set(workspace["package_ids"]) != package_ids or not set(
        workspace["default_package_ids"]
    ) <= package_ids:
        _fail("RustProjectIR v3 workspace package closure drifted")
    module_units = {item["unit_id"] for item in modules.values()}
    if not module_units <= set(candidates):
        _fail("RustProjectIR v3 module candidate closure drifted")
    if status == "ready" and (not packages or module_units != set(candidates)):
        _fail("RustProjectIR v3 ready topology is incomplete")
    target_namespaces: dict[str, str] = {}
    namespace_targets: dict[str, str] = {}
    for module in modules.values():
        package_id, target_id = str(module["package_id"]), str(module["target_id"])
        if package_id not in packages or target_id not in targets:
            _fail("RustProjectIR v3 module owner is unknown")
        if targets[target_id]["package_id"] != package_id:
            _fail("RustProjectIR v3 module package and target disagree")
        namespace = str(module["target_namespace_id"])
        if target_namespaces.setdefault(target_id, namespace) != namespace or (
            namespace_targets.setdefault(namespace, target_id) != target_id
        ):
            _fail("RustProjectIR v3 target namespace closure drifted")
    for package_id, package in packages.items():
        dependencies = set(package["dependency_package_ids"])
        expected_targets = {key for key, item in targets.items() if item["package_id"] == package_id}
        expected_modules = {key for key, item in modules.items() if item["package_id"] == package_id}
        if package_id in dependencies or not dependencies <= package_ids:
            _fail("RustProjectIR v3 package dependency closure drifted")
        if set(package["target_ids"]) != expected_targets or set(package["module_ids"]) != expected_modules:
            _fail("RustProjectIR v3 package topology closure drifted")
        _owner_evidence(package, expected_modules, modules)
    for target_id, target in targets.items():
        if target["package_id"] not in packages:
            _fail("RustProjectIR v3 target package is unknown")
        expected_modules = {key for key, item in modules.items() if item["target_id"] == target_id}
        if set(target["module_ids"]) != expected_modules:
            _fail("RustProjectIR v3 target module closure drifted")
        _owner_evidence(target, expected_modules, modules)
        try:
            occurrence_module_order(target, {key: modules[key]["source_unit_ids"]
                                             for key in expected_modules})
        except ValueError as error:
            _fail(str(error))
        if any(item["dependency_target_id"] is not None and
               item["dependency_target_id"] not in target_ids
               for item in target["input_occurrences"]):
            _fail("RustProjectIR v3 input occurrence target is unknown")


def _interface_sections(value: Mapping[str, Any], modules: Mapping[str, Mapping[str, Any]],
                        candidates: Mapping[str, Mapping[str, Any]],
                        builds: set[str]) -> None:
    for name, id_field in _SECTION_IDS.items():
        records = _indexed(value.get(name), name, id_field, _V2_FIELDS[name])
        for record in records.values():
            _record_shape(name, record)
            evidence = _evidence_sets(record.get("evidence"), candidates, builds)
            owners = record.get("module_ids", [record.get("module_id")])
            if any(owner not in modules for owner in owners):
                _fail("RustProjectIR v3 declaration module is unknown")
            if any(modules[owner]["unit_id"] not in evidence[0] or
                   modules[owner]["candidate_sha256"] not in evidence[1]
                   for owner in owners):
                _fail("RustProjectIR v3 declaration evidence does not bind its module")
        if name == "initialization" and any(
            not set(record["after"]) <= set(records) for record in records.values()
        ):
            _fail("RustProjectIR v3 initialization reference is unknown")


def _topology_state(value: Mapping[str, Any], packages: Mapping[str, Any],
                    targets: Mapping[str, Any], modules: Mapping[str, Any]) -> None:
    status, blockers = value.get("topology_status"), value.get("topology_blockers")
    if status not in {"ready", "blocked"} or not isinstance(blockers, list):
        _fail("RustProjectIR v3 topology state is invalid")
    entities = {
        "workspace": {value["workspace"]["workspace_id"]}, "package": set(packages),
        "target": set(targets), "module": set(modules),
    }
    keys = []
    for blocker in blockers:
        if not isinstance(blocker, Mapping) or set(blocker) != {
            "code", "entity_kind", "entity_id",
        }:
            _fail("RustProjectIR v3 topology blocker schema is invalid")
        key = tuple(_text(blocker[field], f"topology blocker {field}")
                    for field in ("code", "entity_kind", "entity_id"))
        if key[1] not in entities or key[2] not in entities[key[1]]:
            _fail("RustProjectIR v3 topology blocker entity is unknown")
        keys.append(key)
    if keys != sorted(set(keys)):
        _fail("RustProjectIR v3 topology blockers are not canonical")
    if (status == "ready" and blockers) or (status == "blocked" and not blockers):
        _fail("RustProjectIR v3 topology status and blockers disagree")


def _indexed(value: Any, label: str, id_field: str,
             fields: set[str]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        _fail(f"RustProjectIR v3 {label} must be an array")
    result: dict[str, Mapping[str, Any]] = {}
    for record in value:
        if not isinstance(record, Mapping) or set(record) != fields:
            _fail(f"RustProjectIR v3 {label} entry schema is invalid")
        identity = _text(record.get(id_field), f"{label} identity")
        if identity in result:
            _fail(f"RustProjectIR v3 {label} identities must be unique")
        result[identity] = record
    if value != sorted(value, key=lambda item: item[id_field]):
        _fail(f"RustProjectIR v3 {label} is not canonical")
    return result


def _evidence_sets(value: Any, candidates: Mapping[str, Mapping[str, Any]], builds: set[str]
                   ) -> tuple[set[str], set[str], set[str]]:
    _evidence(value, candidates, builds)
    return (set(value["dag_unit_ids"]), set(value["candidate_sha256s"]),
            set(value["build_ir_sha256s"]))


def _owner_evidence(owner: Mapping[str, Any], module_ids: set[str],
                    modules: Mapping[str, Mapping[str, Any]]) -> None:
    evidence = owner["evidence"]
    if any(modules[key]["unit_id"] not in evidence["dag_unit_ids"] or
           modules[key]["candidate_sha256"] not in evidence["candidate_sha256s"]
           for key in module_ids):
        _fail("RustProjectIR v3 owner evidence does not cover its modules")


def _occurrences(target: Mapping[str, Any]) -> None:
    value = target.get("input_occurrences")
    if not isinstance(value, list):
        _fail("RustProjectIR v3 input_occurrences must be an array")
    try:
        explicit_order = occurrence_module_order(target)
    except ValueError as error:
        _fail(str(error))
    build_shas = target["evidence"]["build_ir_sha256s"]
    if explicit_order is not None and len(build_shas) != 1:
        _fail("RustProjectIR v3 occurrence BuildIR binding is ambiguous")
    ordinals = []
    for item in value:
        ordinal = item.get("ordinal")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
            _fail("RustProjectIR v3 input occurrence ordinal is invalid")
        _text(item.get("role"), "input occurrence role")
        if item.get("dependency_target_id") is not None:
            _text(item["dependency_target_id"], "input occurrence dependency_target_id")
        if explicit_order is not None and item["occurrence_id"] != input_occurrence_id(
            build_shas[0], target["build_ir_target_id"], ordinal,
        ):
            _fail("RustProjectIR v3 occurrence identity is invalid")
        _sha(item.get("binding_sha256"), "input occurrence binding_sha256")
        ordinals.append(ordinal)
    if ordinals != list(range(len(value))):
        _fail("RustProjectIR v3 input occurrences are not canonical")


def _ordered_strings(value: Any, label: str) -> None:
    if not isinstance(value, list):
        _fail(f"RustProjectIR v3 {label} must be a string array")
    for item in value:
        _text(item, label)


def _fail(message: str) -> None:
    raise RustProjectIRError(message)


__all__ = ["module_id_for_target_candidate", "validate_v3_sections"]
