from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from . import cargo_project
from .artifacts import content_sha256
from .rust_project_ir import canonical_rust_project_ir_bytes
from .rust_project_native_cargo import (
    native_link_build_script, native_link_generation_binding,
)


GENERATOR = "deterministic-rust-project-ir-cargo-v1"
RUST_PROJECT_IR_FILE = "migration-rust-project-ir.json"


def render_cargo_project(
    ir: Mapping[str, Any], binding: Mapping[str, Any],
    coordination: Mapping[str, Any], dependencies: Mapping[str, tuple[str, ...]],
    order: list[str], candidates: list[cargo_project.CandidateSource],
    unsafe_policy: Mapping[str, Any], scope: str,
) -> cargo_project.CargoProjectPlan:
    by_unit = {item.group_id: item for item in candidates}
    module_by_unit = {str(item["unit_id"]): item for item in ir["modules"]}
    conditions = _module_conditions(ir)
    build_script = native_link_build_script(ir)
    files: dict[str, bytes] = {
        "Cargo.toml": _cargo_toml(ir, has_build_script=build_script is not None),
        "Cargo.lock": _cargo_lock(str(ir["crate"]["crate_id"])),
        RUST_PROJECT_IR_FILE: canonical_rust_project_ir_bytes(ir),
    }
    if build_script is not None:
        files["build.rs"] = build_script
    lines = ["// Generated only from a validated RustProjectIR.", ""]
    groups = []
    for unit_id in order:
        candidate = by_unit[unit_id]
        module = module_by_unit[unit_id]
        module_id = str(module["module_id"])
        condition = conditions.get(module_id)
        if condition:
            lines.append(f"#[cfg({condition})]")
        lines.append(f"mod {candidate.module_name};")
        if candidate.public_symbols:
            if condition:
                lines.append(f"#[cfg({condition})]")
            lines.append(
                f"pub use self::{candidate.module_name}::"
                f"{{{', '.join(candidate.public_symbols)}}};"
            )
        lines.append("")
        files[str(module["rust_path"])] = candidate.source
        groups.append({
            "group_id": unit_id, "module_name": candidate.module_name,
            "dependencies": list(dependencies[unit_id]),
            "source": {
                "path": candidate.source_path, "sha256": candidate.sha256,
                "size_bytes": len(candidate.source),
            },
            "public_symbols": list(candidate.public_symbols),
            "required_symbols": list(candidate.required_symbols),
            "unsafe_count": candidate.unsafe_count,
        })
    files["src/lib.rs"] = ("\n".join(lines).rstrip() + "\n").encode("ascii")
    refs = [_ref(path, data) for path, data in sorted(files.items())]
    dag_payload = {
        "dependencies": {
            key: list(dependencies[key]) for key in sorted(dependencies)
        },
        "order": order,
    }
    manifest = {
        "schema_version": 1, "generator": GENERATOR,
        "rust_project_ir_scope": scope,
        "rust_project_ir_sha256": ir["ir_sha256"],
        "rust_project_interface_sha256": ir["interface_sha256"],
        "rust_project_ir_completeness": dict(ir["interface_completeness"]),
        "domain_binding_sha256": content_sha256(binding),
        "interface_coordination_sha256": content_sha256(coordination),
        "dag_sha256": hashlib.sha256(
            cargo_project.canonical_json_bytes(dag_payload)
        ).hexdigest(),
        "native_link": native_link_generation_binding(ir, build_script),
        "accepted_groups": groups, "unsafe_policy": dict(unsafe_policy),
        "cargo_executed": False, "files": refs,
    }
    files[cargo_project.LAST_GOOD_MANIFEST] = cargo_project.canonical_json_bytes(
        manifest
    )
    return cargo_project.CargoProjectPlan(files=files, last_good_manifest=manifest)


def _module_conditions(ir: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, list[str]] = {}
    for item in ir["cfgs"]:
        for module_id in item["module_ids"]:
            values.setdefault(str(module_id), []).append(str(item["expression"]))
    feature_modules: dict[str, list[str]] = {}
    for item in ir["features"]:
        for module_id in item["module_ids"]:
            feature_modules.setdefault(str(module_id), []).append(str(item["name"]))
    result = {}
    for module in ir["modules"]:
        module_id = str(module["module_id"])
        parts = sorted(values.get(module_id, []))
        names = sorted(feature_modules.get(module_id, []))
        if names:
            feature = ", ".join(f'feature = "{name}"' for name in names)
            parts.append(f"any({feature})" if len(names) > 1 else feature)
        if parts:
            result[module_id] = (
                f"all({', '.join(parts)})" if len(parts) > 1 else parts[0]
            )
    return result


def _cargo_toml(
    ir: Mapping[str, Any], *, has_build_script: bool,
) -> bytes:
    crate = ir["crate"]
    lines = [
        "[package]", f'name = "{crate["crate_id"]}"', 'version = "0.0.0"',
        f'edition = "{crate["edition"]}"', "publish = false", "", "[lib]",
        'path = "src/lib.rs"',
        "crate-type = ["
        + ", ".join(f'"{item}"' for item in crate["crate_types"])
        + "]",
        "", "[features]",
    ]
    if has_build_script:
        lines[5:5] = ['build = "build.rs"']
    features = {item["feature_id"]: item for item in ir["features"]}
    defaults = sorted(
        str(item["name"]) for item in features.values() if item["default"]
    )
    lines.append("default = [" + ", ".join(f'"{item}"' for item in defaults) + "]")
    for item in sorted(features.values(), key=lambda value: str(value["name"])):
        enabled = [
            str(features[feature_id]["name"]) for feature_id in item["enables"]
        ]
        lines.append(
            f'{item["name"]} = ['
            + ", ".join(f'"{name}"' for name in enabled)
            + "]"
        )
    return ("\n".join(lines) + "\n").encode("ascii")


def _cargo_lock(crate_name: str) -> bytes:
    return (
        "# This file is automatically @generated by Cargo.\n"
        "# It is not intended for manual editing.\nversion = 3\n\n"
        f'[[package]]\nname = "{crate_name}"\nversion = "0.0.0"\n'
    ).encode("ascii")


def _ref(path: str, data: bytes) -> dict[str, Any]:
    return {
        "path": path, "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


__all__ = ["GENERATOR", "RUST_PROJECT_IR_FILE", "render_cargo_project"]
