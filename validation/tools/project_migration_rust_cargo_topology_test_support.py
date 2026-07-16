from __future__ import annotations

import hashlib
import json

from validation.tools._project_migration_harness.rust_occurrence_manifest import (
    occurrence_manifest_bytes,
)
from validation.tools._project_migration_harness.rust_project_cargo_v3_projection_analysis import (
    root_path,
)
from validation.tools._project_migration_harness.rust_project_cargo_v3_projection_validation import (
    module_identifier, package_member_path,
)
from validation.tools.project_migration_rust_link_product_test_support import (
    ET_DYN, ET_EXEC, ar_member, archive, elf_product, relocatable_elf,
)


def check(command: list[str], raw: bytes, reference: dict) -> dict:
    return {
        "command": list(command), "status": "passed",
        "stdout_sha256": hashlib.sha256(raw).hexdigest(),
        "stdout_ref": reference,
    }


def metadata_raw(facts: dict) -> bytes:
    packages = []
    identities = []
    for package in facts["packages"]:
        identity = package_id(package["name"])
        identities.append(identity)
        packages.append({
            "id": identity, "name": package["name"],
            "version": package["version"], "features": {},
            "targets": [{
                "name": target["name"], "kind": target["kind"],
                "crate_types": target["crate_types"],
                "required-features": target["required_features"],
            } for target in package["targets"]],
        })
    defaults = {
        (item["name"], item["version"]) for item in facts["default_members"]
    }
    root = {
        "metadata": None, "packages": packages, "resolve": None,
        "target_directory": "/workspace/target", "version": 1,
        "workspace_default_members": [
            identity for identity, package in zip(identities, packages, strict=True)
            if (package["name"], package["version"]) in defaults
        ],
        "workspace_members": identities, "workspace_root": "/workspace",
    }
    return json_bytes(root)


def compiler_raw(facts: dict, ir: dict, *, fresh: bool) -> bytes:
    events = []
    for package in facts["packages"]:
        for target in package["targets"]:
            ir_target = ir_target_for_package(ir, package["name"])
            filename = f"/workspace/target/debug/{target['name']}.rmeta"
            compiler_target = target_facts(target, ir_target)
            artifact = {
                "reason": "compiler-artifact",
                "package_id": package_id(package["name"]),
                "manifest_path": f"/workspace/{package['name']}/Cargo.toml",
                "target": compiler_target,
                "profile": {
                    "opt_level": "0", "debuginfo": 2,
                    "debug_assertions": True, "overflow_checks": True,
                    "test": False,
                },
                "features": [], "filenames": [filename],
                "executable": None, "fresh": fresh,
            }
            events.append(artifact)
            if set(target["kind"]) & {"bin", "cdylib"}:
                events.append({
                    "reason": "compiler-message",
                    "package_id": artifact["package_id"],
                    "manifest_path": artifact["manifest_path"],
                    "target": compiler_target,
                    "message": {
                        "level": "warning", "code": {"code": "linker_messages"},
                        "message": "linker stdout: /usr/lib/crt1.o\n",
                    },
                })
    events.append({"reason": "build-finished", "success": True})
    return b"".join(json_bytes(event) + b"\n" for event in events)


def captured_products(facts: dict, ir: dict) -> list[dict]:
    result = []
    for package in facts["packages"]:
        for target in package["targets"]:
            ir_target = ir_target_for_package(ir, package["name"])
            compiler_target = target_facts(target, ir_target)
            kinds = set(target["crate_types"]) & {
                "bin", "cdylib", "rlib", "staticlib",
            }
            if "lib" in target["crate_types"] and "rlib" not in kinds:
                kinds.add("rlib")
            for kind in sorted(kinds):
                guest = f"/runtime/target/debug/{package['name']}-{kind}"
                result.append({
                    "package_id": package_id(package["name"]),
                    "target": compiler_target, "product_kind": kind,
                    "guest_path_sha256": hashlib.sha256(
                        guest.encode("utf-8"),
                    ).hexdigest(),
                    "data": product_bytes(
                        kind, occurrence_manifest_bytes(ir_target),
                    ),
                })
    return result


def captured_dep_info(facts: dict, ir: dict) -> list[dict]:
    result = []
    modules = {item["module_id"]: item for item in ir["modules"]}
    for package in facts["packages"]:
        for target in package["targets"]:
            ir_target = ir_target_for_package(ir, package["name"])
            compiler_target = target_facts(target, ir_target)
            kind = primary_kind(target["crate_types"])
            guest = f"/runtime/target/debug/{package['name']}-{kind}"
            module_paths = [
                module_path(ir_target, modules[module_id])
                for module_id in ir_target["module_ids"]
            ]
            raw = f"{guest}: {' '.join([target_root(ir_target), *module_paths])}\n"
            result.append({
                "package_id": package_id(package["name"]),
                "target": compiler_target,
                "product_guest_path_sha256": hashlib.sha256(
                    guest.encode("utf-8"),
                ).hexdigest(),
                "dep_info_guest_path_sha256": hashlib.sha256(
                    f"{guest}.d".encode("utf-8"),
                ).hexdigest(),
                "data": raw.encode("utf-8"),
            })
    return result


def product_bytes(kind: str, marker: bytes) -> bytes:
    relocatable = relocatable_elf()
    if kind == "staticlib":
        return archive(ar_member("unit.o/", relocatable + marker))
    if kind == "rlib":
        return archive(
            ar_member("lib.rmeta/", relocatable),
            ar_member("unit.o/", relocatable + b"code" + marker),
        )
    if kind == "cdylib":
        return elf_product(ET_DYN, executable_entry=False) + marker
    return elf_product(ET_EXEC) + marker


def primary_kind(crate_types: list[str]) -> str:
    for kind in ("bin", "rlib", "staticlib", "cdylib"):
        if kind in crate_types:
            return kind
    raise AssertionError("test target has no dep-info product")


def target_facts(target: dict, ir_target: dict) -> dict:
    return {
        "kind": target["kind"], "crate_types": target["crate_types"],
        "name": target["name"], "src_path": target_root(ir_target),
        "edition": "2021", "doc": True, "doctest": True, "test": True,
    }


def target_root(target: dict) -> str:
    return f"/workspace/{root_path(target['package_id'], target['kind'])}"


def module_path(target: dict, module: dict) -> str:
    return (
        f"/workspace/{package_member_path(target['package_id'])}"
        f"/src/modules/{module_identifier(module['module_id'])}.rs"
    )


def ir_target_for_package(ir: dict, package_name: str) -> dict:
    package = next(item for item in ir["packages"] if item["name"] == package_name)
    target_id = package["target_ids"][0]
    return next(item for item in ir["targets"] if item["target_id"] == target_id)


def package_id(name: str) -> str:
    return f"path+file:///workspace/{name}#{name}@0.0.0"


def json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
