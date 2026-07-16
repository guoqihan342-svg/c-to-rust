from __future__ import annotations

import hashlib
import json

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.rust_project_ir_v3 import (
    build_rust_project_ir_v3,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_validation import (
    module_id_for_target_candidate,
)


BUILD_SHA = "b" * 64
LINK_KEYS = ("app", "alpha", "beta", "gamma")
DEPENDENCIES = ("alpha", "beta")


def rust_project_ir(*, static_only: bool = False) -> dict:
    keys = ("static",) if static_only else LINK_KEYS
    sources = {
        key: (
            b"fn main() {}\n" if key == "app"
            else f"pub fn {key}_value() -> i32 {{ 1 }}\n".encode("ascii")
        )
        for key in keys
    }
    source_shas = {
        key: hashlib.sha256(source).hexdigest()
        for key, source in sources.items()
    }
    modules = {}
    for key in keys:
        unit_id = f"unit-{key}"
        source_unit_id = f"source-{key}"
        module_id = module_id_for_target_candidate(
            f"namespace-{key}", unit_id, source_shas[key], [source_unit_id],
        )
        modules[key] = {
            "module_id": module_id,
            "package_id": f"package-{key}",
            "target_id": f"target-{key}",
            "target_namespace_id": f"namespace-{key}",
            "rust_path": f"packages/package-{key}/src/{module_id}.rs",
            "unit_id": unit_id,
            "source_unit_ids": [source_unit_id],
            "candidate_sha256": source_shas[key],
            "visibility": "crate",
            "evidence": _evidence([unit_id], [source_shas[key]]),
        }
    packages = []
    targets = []
    for key in keys:
        module = modules[key]
        linkable = key == "app"
        crate_types = (
            ["bin"] if linkable else
            ["staticlib"] if static_only else ["rlib"]
        )
        dependencies = list(DEPENDENCIES) if linkable else []
        packages.append({
            "package_id": f"package-{key}",
            "name": package_name(key),
            "build_ir_target_id": f"build-target-{key}",
            "product_kind": "executable" if linkable else "static-library",
            "dependency_package_ids": [
                f"package-{item}" for item in dependencies
            ],
            "target_ids": [f"target-{key}"],
            "module_ids": [module["module_id"]],
            "evidence": module["evidence"],
        })
        targets.append({
            "target_id": f"target-{key}",
            "package_id": f"package-{key}",
            "name": target_name(key),
            "kind": "bin" if linkable else "lib",
            "crate_types": crate_types,
            "build_ir_target_id": f"build-target-{key}",
            "module_ids": [module["module_id"]],
            "input_occurrences": [
                {
                    "ordinal": ordinal,
                    "role": "link-input",
                    "dependency_target_id": f"target-{dependency}",
                    "binding_sha256": _sha(f"binding-{dependency}"),
                }
                for ordinal, dependency in enumerate(dependencies)
            ],
            "ordered_link_arguments": [],
            "evidence": module["evidence"],
        })
    candidate_refs = [
        {
            "unit_id": f"unit-{key}",
            "artifact_id": f"candidate-{key}",
            "source": {
                "path": f"candidates/{key}.rs",
                "sha256": source_shas[key],
                "size_bytes": len(sources[key]),
            },
        }
        for key in keys
    ]
    reference = lambda path, digest: {
        "path": path, "sha256": digest, "size_bytes": 1,
    }
    return build_rust_project_ir_v3(
        migration_dag_ref=reference("plan/dag.json", "a" * 64),
        migration_graph_ref=reference("plan/graph.json", "c" * 64),
        build_ir_refs=[reference("plan/build.json", BUILD_SHA)],
        candidate_refs=candidate_refs,
        workspace={
            "workspace_id": "generic-workspace",
            "resolver": "2",
            "package_ids": [f"package-{key}" for key in keys],
            "default_package_ids": [f"package-{key}" for key in keys],
            "evidence": _evidence(
                [f"unit-{key}" for key in keys],
                [source_shas[key] for key in keys],
            ),
        },
        packages=packages,
        targets=targets,
        modules=list(modules.values()),
    )


def cargo_stream(
    *,
    diagnostics: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
    noise: str | None = None,
    static_only: bool = False,
) -> bytes:
    keys = ("static",) if static_only else LINK_KEYS
    events = [_artifact(key) for key in keys]
    if noise is not None:
        events.append(_message("app", (), code="unused_warning", text=noise))
    if diagnostics is None and not static_only:
        diagnostics = (("app", DEPENDENCIES),)
    for owner, order in diagnostics or ():
        events.append(_message(owner, order))
    events.append({"reason": "build-finished", "success": True})
    return b"".join(_json(event) + b"\n" for event in events)


def rust_products(*, static_only: bool = False) -> list[dict]:
    keys = ("static",) if static_only else LINK_KEYS
    return [_product(key) for key in keys]


def package_id(key: str) -> str:
    return (
        f"path+file:///workspace/packages/{key}#"
        f"{package_name(key)}@0.0.0"
    )


def package_name(key: str) -> str:
    return f"generic_{key}"


def target_name(key: str) -> str:
    return f"{key}_target"


def artifact_path(key: str) -> str:
    if key == "app":
        return "/runtime/target/debug/app_target"
    if key == "static":
        return "/runtime/target/debug/libstatic_target.a"
    return f"/runtime/target/debug/deps/lib{key}_target-{key}1.rlib"


def path_sha256(key: str) -> str:
    return _sha(artifact_path(key))


def _artifact(key: str) -> dict:
    target = _target(key)
    executable = artifact_path(key) if key == "app" else None
    return {
        "reason": "compiler-artifact",
        "package_id": package_id(key),
        "manifest_path": f"/workspace/packages/{key}/Cargo.toml",
        "target": target,
        "profile": {
            "opt_level": "0", "debuginfo": 2,
            "debug_assertions": True, "overflow_checks": True,
            "test": False,
        },
        "features": [], "filenames": [artifact_path(key)],
        "executable": executable, "fresh": False,
    }


def _target(key: str) -> dict:
    if key == "app":
        kind, crate_types = ["bin"], ["bin"]
    elif key == "static":
        kind, crate_types = ["staticlib"], ["staticlib"]
    else:
        kind, crate_types = ["lib"], ["rlib"]
    return {
        "kind": kind, "crate_types": crate_types,
        "name": target_name(key),
        "src_path": f"/workspace/packages/{key}/src/lib.rs",
        "edition": "2021", "doc": True, "doctest": True, "test": True,
    }


def _message(
    owner: str,
    order: tuple[str, ...],
    *,
    code: str = "linker_messages",
    text: str | None = None,
) -> dict:
    body = "\n".join(artifact_path(key) for key in order)
    message = text if text is not None else f"linker stdout: {body}"
    return {
        "reason": "compiler-message",
        "package_id": package_id(owner),
        "manifest_path": f"/workspace/packages/{owner}/Cargo.toml",
        "target": _target(owner),
        "message": {
            "level": "warning", "code": {"code": code},
            "message": message,
        },
    }


def _product(key: str) -> dict:
    data_sha = _sha(f"product-{key}")
    target = _target(key)
    product_kind = target["crate_types"][0]
    core = {
        "schema_version": 1,
        "package": {
            "name": package_name(key), "version": "0.0.0",
            "package_id_sha256": _sha(package_id(key)),
        },
        "target": {
            "name": target_name(key), "kind": target["kind"],
            "crate_types": target["crate_types"],
        },
        "product_kind": product_kind,
        "guest_path_sha256": path_sha256(key),
        "file": {
            "path": f"verification/rust-products/{data_sha}.bin",
            "sha256": data_sha, "size_bytes": 1,
        },
    }
    return {**core, "product_sha256": content_sha256(core)}


def _evidence(units: list[str], candidates: list[str]) -> dict:
    return {
        "build_ir_sha256s": [BUILD_SHA],
        "dag_unit_ids": sorted(units),
        "candidate_sha256s": sorted(candidates),
    }


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "DEPENDENCIES", "artifact_path", "cargo_stream", "package_id",
    "package_name", "path_sha256", "rust_products", "rust_project_ir",
    "target_name",
]
