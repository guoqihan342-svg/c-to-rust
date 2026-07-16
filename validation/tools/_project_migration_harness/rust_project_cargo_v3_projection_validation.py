from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .rust_project_cargo_v3_projection_ready import validate_ready_projection


SCHEMA_VERSION = 1
ARTIFACT_KIND = "rust-project-cargo-v3-workspace-projection"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_TOP_KEYS = {
    "schema_version", "artifact_kind", "rust_project_ir_sha256",
    "source_layout_sha256", "workspace", "packages", "targets", "modules",
    "status", "blockers", "claim_boundary", "projection_sha256",
}
_WORKSPACE_KEYS = {
    "workspace_id", "resolver", "member_paths", "default_member_paths",
}
_PACKAGE_KEYS = {
    "package_id", "name", "manifest_path", "build_ir_target_id",
    "product_kind", "dependency_package_ids", "dependency_aliases",
    "target_ids", "module_ids",
}
_TARGET_KEYS = {
    "target_id", "package_id", "name", "kind", "build_ir_target_id",
    "crate_types", "root_path", "entry_module_id", "module_ids", "input_occurrences",
    "ordered_link_arguments", "export_namespace_sha256",
}
_MODULE_KEYS = {
    "module_id", "package_id", "target_id", "unit_id", "identifier",
    "source_path", "render_path", "source_sha256", "top_level_names",
    "binary_entry_count", "test_entry_count",
}
_OCCURRENCE_KEYS = {
    "ordinal", "role", "dependency_target_id", "binding_sha256",
}
_BLOCKER_KEYS = {"code", "entity_kind", "entity_id"}
_PRODUCT_KINDS = {"static-library", "shared-library", "executable"}
_TARGET_KINDS = {"lib", "cdylib", "bin"}


def module_identifier(module_id: str) -> str:
    """Encode the complete module identity without using candidate content."""
    _text(module_id, "module_id")
    encoded = "".join(
        char if char.isascii() and (char.isalnum() or char == "_") else "_"
        for char in module_id
    )
    return f"module_{encoded}"


def cargo_alias(package_name: str) -> str:
    _text(package_name, "package name")
    return package_name.replace("-", "_")


def package_member_path(package_id: str) -> str:
    return f"packages/{package_id}"


def validate_rust_project_cargo_v3_projection(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        _fail("Cargo v3 projection top-level schema is invalid")
    if value.get("schema_version") != SCHEMA_VERSION:
        _fail("Cargo v3 projection schema version is unsupported")
    if value.get("artifact_kind") != ARTIFACT_KIND:
        _fail("Cargo v3 projection artifact kind is invalid")
    _sha(value.get("rust_project_ir_sha256"), "rust_project_ir_sha256")
    _sha(value.get("source_layout_sha256"), "source_layout_sha256")
    workspace = _workspace(value.get("workspace"))
    packages = _indexed(value.get("packages"), "packages", "package_id", _PACKAGE_KEYS)
    targets = _indexed(value.get("targets"), "targets", "target_id", _TARGET_KEYS)
    modules = _indexed(value.get("modules"), "modules", "module_id", _MODULE_KEYS)
    _packages(packages)
    _targets(targets)
    _modules(modules)
    _closure(workspace, packages, targets, modules)
    blockers = _blockers(value.get("blockers"), workspace, packages, targets, modules)
    status = value.get("status")
    if status not in {"ready", "blocked"}:
        _fail("Cargo v3 projection status is invalid")
    if (status == "ready") != (not blockers):
        _fail("Cargo v3 projection status and blockers disagree")
    if value.get("claim_boundary") is not False:
        _fail("Cargo v3 projection claim boundary must be false")
    if status == "ready":
        validate_ready_projection(packages, targets, modules)
    payload = {key: item for key, item in value.items() if key != "projection_sha256"}
    if content_sha256(payload) != _sha(value.get("projection_sha256"), "projection_sha256"):
        _fail("Cargo v3 projection hash drifted")


def _workspace(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _WORKSPACE_KEYS:
        _fail("Cargo v3 projection workspace schema is invalid")
    _text(value.get("workspace_id"), "workspace_id")
    _text(value.get("resolver"), "resolver")
    _strings(value.get("member_paths"), "member_paths")
    _strings(value.get("default_member_paths"), "default_member_paths")
    for path in [*value["member_paths"], *value["default_member_paths"]]:
        checked_relative_path(path)
    return value


def _packages(values: Mapping[str, Mapping[str, Any]]) -> None:
    for package in values.values():
        for field in ("name", "build_ir_target_id"):
            _text(package.get(field), f"package.{field}")
        checked_relative_path(package.get("manifest_path"))
        if package.get("product_kind") not in _PRODUCT_KINDS:
            _fail("Cargo v3 projection product kind is invalid")
        for field in ("dependency_package_ids", "target_ids", "module_ids"):
            _strings(package.get(field), f"package.{field}")
        aliases = package.get("dependency_aliases")
        if not isinstance(aliases, Mapping) or set(aliases) != set(
            package["dependency_package_ids"]
        ):
            _fail("Cargo v3 projection dependency aliases are invalid")
        for package_id, alias in aliases.items():
            _text(package_id, "dependency alias package_id")
            _text(alias, "dependency alias")


def _targets(values: Mapping[str, Mapping[str, Any]]) -> None:
    for target in values.values():
        for field in ("package_id", "name", "build_ir_target_id"):
            _text(target.get(field), f"target.{field}")
        if target.get("kind") not in _TARGET_KINDS:
            _fail("Cargo v3 projection target kind is invalid")
        _strings(target.get("crate_types"), "target.crate_types", nonempty=True)
        checked_relative_path(target.get("root_path"))
        entry = target.get("entry_module_id")
        if entry is not None:
            _text(entry, "target.entry_module_id")
        _strings(target.get("module_ids"), "target.module_ids")
        _occurrences(target.get("input_occurrences"))
        _ordered_strings(target.get("ordered_link_arguments"), "ordered_link_arguments")
        _sha(target.get("export_namespace_sha256"), "export_namespace_sha256")


def _modules(values: Mapping[str, Mapping[str, Any]]) -> None:
    for module_id, module in values.items():
        for field in ("package_id", "target_id", "unit_id"):
            _text(module.get(field), f"module.{field}")
        identifier = _text(module.get("identifier"), "module.identifier")
        if identifier != module_identifier(module_id) or not _IDENTIFIER.fullmatch(identifier):
            _fail("Cargo v3 projection module identifier is invalid")
        for field in ("source_path", "render_path"):
            checked_relative_path(module.get(field))
        _sha(module.get("source_sha256"), "module.source_sha256")
        _ordered_strings(module.get("top_level_names"), "module.top_level_names")
        if module["top_level_names"] != sorted(module["top_level_names"]):
            _fail("Cargo v3 projection top-level names are not canonical")
        for field in ("binary_entry_count", "test_entry_count"):
            _count(module.get(field), f"module.{field}")


def _closure(workspace, packages, targets, modules) -> None:
    package_ids = set(packages)
    expected_members = [package_member_path(key) for key in sorted(packages)]
    if workspace["member_paths"] != expected_members:
        _fail("Cargo v3 projection workspace member closure drifted")
    if not set(workspace["default_member_paths"]) <= set(expected_members):
        _fail("Cargo v3 projection default member closure drifted")
    for package_id, package in packages.items():
        if package_id in package["dependency_package_ids"] or not set(
            package["dependency_package_ids"]
        ) <= package_ids:
            _fail("Cargo v3 projection package dependency closure drifted")
        expected_targets = {key for key, item in targets.items() if item["package_id"] == package_id}
        expected_modules = {key for key, item in modules.items() if item["package_id"] == package_id}
        if set(package["target_ids"]) != expected_targets or set(package["module_ids"]) != expected_modules:
            _fail("Cargo v3 projection package ownership drifted")
        if package["manifest_path"] != f"{package_member_path(package_id)}/Cargo.toml":
            _fail("Cargo v3 projection manifest path drifted")
        expected_aliases = {
            key: cargo_alias(str(packages[key]["name"]))
            for key in package["dependency_package_ids"]
        }
        if dict(package["dependency_aliases"]) != expected_aliases:
            _fail("Cargo v3 projection dependency alias derivation drifted")
    for target_id, target in targets.items():
        package_id = target["package_id"]
        if package_id not in packages:
            _fail("Cargo v3 projection target package is unknown")
        owned = {key for key, item in modules.items() if item["target_id"] == target_id}
        if set(target["module_ids"]) != owned or any(
            modules[key]["package_id"] != package_id for key in owned
        ):
            _fail("Cargo v3 projection target ownership drifted")
        root = "main.rs" if target["kind"] == "bin" else "lib.rs"
        if target["root_path"] != f"{package_member_path(package_id)}/src/{root}":
            _fail("Cargo v3 projection target root path drifted")
    for module_id, module in modules.items():
        if module["target_id"] not in targets or module["package_id"] not in packages:
            _fail("Cargo v3 projection module owner is unknown")
        expected = (
            f"{package_member_path(str(module['package_id']))}/src/modules/"
            f"{module_identifier(module_id)}.rs"
        )
        if module["render_path"] != expected:
            _fail("Cargo v3 projection module render path drifted")


def _blockers(value, workspace, packages, targets, modules) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        _fail("Cargo v3 projection blockers must be an array")
    entities = {
        "workspace": {workspace["workspace_id"]}, "package": set(packages),
        "target": set(targets), "module": set(modules),
    }
    keys = []
    for blocker in value:
        if not isinstance(blocker, Mapping) or set(blocker) != _BLOCKER_KEYS:
            _fail("Cargo v3 projection blocker schema is invalid")
        key = tuple(_text(blocker.get(field), f"blocker.{field}")
                    for field in ("code", "entity_kind", "entity_id"))
        if key[1] not in entities or key[2] not in entities[key[1]]:
            _fail("Cargo v3 projection blocker entity is unknown")
        keys.append(key)
    if keys != sorted(set(keys)):
        _fail("Cargo v3 projection blockers are not canonical")
    return value


def _indexed(value, label, identity, fields):
    if not isinstance(value, list):
        _fail(f"Cargo v3 projection {label} must be an array")
    result = {}
    for item in value:
        if not isinstance(item, Mapping) or set(item) != fields:
            _fail(f"Cargo v3 projection {label} entry schema is invalid")
        key = _text(item.get(identity), f"{label} identity")
        if key in result:
            _fail(f"Cargo v3 projection {label} identities must be unique")
        result[key] = item
    if value != sorted(value, key=lambda item: item[identity]):
        _fail(f"Cargo v3 projection {label} is not canonical")
    return result


def _occurrences(value: Any) -> None:
    if not isinstance(value, list):
        _fail("Cargo v3 projection input occurrences must be an array")
    for ordinal, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != _OCCURRENCE_KEYS:
            _fail("Cargo v3 projection input occurrence schema is invalid")
        if item.get("ordinal") != ordinal:
            _fail("Cargo v3 projection input occurrence order drifted")
        _text(item.get("role"), "input occurrence role")
        if item.get("dependency_target_id") is not None:
            _text(item["dependency_target_id"], "input occurrence dependency target")
        _sha(item.get("binding_sha256"), "input occurrence binding_sha256")


def _strings(value, label, *, nonempty=False):
    _ordered_strings(value, label)
    if (nonempty and not value) or value != sorted(set(value)):
        _fail(f"Cargo v3 projection {label} is not a canonical set")


def _ordered_strings(value, label):
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        _fail(f"Cargo v3 projection {label} must be a string array")


def _count(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"Cargo v3 projection {label} is invalid")


def _text(value, label):
    if not isinstance(value, str) or not value or len(value) > 1_024 or any(
        ord(char) < 32 for char in value
    ):
        _fail(f"Cargo v3 projection {label} must be bounded text")
    return value


def _sha(value, label):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _fail(f"Cargo v3 projection {label} is invalid")
    return value


def _fail(message: str) -> None:
    raise ValueError(message)


__all__ = [
    "ARTIFACT_KIND", "SCHEMA_VERSION", "cargo_alias", "module_identifier",
    "package_member_path", "validate_rust_project_cargo_v3_projection",
]
