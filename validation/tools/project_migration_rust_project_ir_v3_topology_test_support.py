from __future__ import annotations

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.build_ir_external_dependencies import (
    project_link_external_dependencies,
)
from validation.tools._project_migration_harness.build_ir_link_occurrences import (
    project_link_authority,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_topology import (
    derive_rust_project_ir_v3_topology,
)


SEMANTIC = "1" * 64
ARTIFACT = "a" * 64


def _derive(builds, scopes, candidates):
    return derive_rust_project_ir_v3_topology(
        builds, scopes, candidates,
        build_ir_binding_sha256s={
            item["semantic_sha256"]: ARTIFACT for item in builds
        },
    )


def _unit(unit_id, *, source=None, index=0, count=1):
    source = source or {
        "path": f"src/{unit_id}.c", "sha256": content_sha256(unit_id),
    }
    return {"unit_id": unit_id, "variant_index": index, "variant_count": count,
            "source": dict(source)}


def _product(target_id, kind, inputs, arguments, *, name=None):
    occurrences = [{
        "ordinal": index, "role": "link-input", "dependency_target_id": dependency,
        "binding": {"path": f"build/{dependency}", "kind": "file",
                    "materialized": True, "sha256": content_sha256(dependency),
                    "size_bytes": 1},
    } for index, dependency in enumerate(inputs)]
    return {
        "target_id": target_id, "name": name or target_id, "kind": kind,
        "dependency_target_ids": list(dict.fromkeys(inputs)),
        "ordered_inputs": occurrences, "ordered_link_arguments": list(arguments),
        "toolchain_id": "link-driver" if kind == "link" else "archiver",
    }


def _build(units, products, *, semantic=SEMANTIC, driver=True):
    objects = [{"target_id": f"obj-{item['unit_id']}", "name": item["unit_id"],
                "kind": "object", "dependency_target_ids": [],
                "ordered_inputs": [], "ordered_link_arguments": []}
               for item in units]
    toolchains = ([{"toolchain_id": "link-driver", "role": "linker-driver"}]
                  if driver else [])
    external_dependencies = []
    for target in products:
        arguments = list(target["ordered_link_arguments"])
        offset = 1 if target["kind"] == "archive" else 0
        raw = {
            "inputs": [dict(item["binding"]) for item in target["ordered_inputs"]],
            "search_roots": [], "ordered_system_link_args": arguments,
            "external_native_libraries": [],
            "ordered_link_occurrences": [
                {"ordinal": ordinal, "argument_index": offset + ordinal,
                 "argument_count": 1, "kind": "input",
                 "reference_ordinal": ordinal}
                for ordinal in range(len(target["ordered_inputs"]))
            ],
        }
        raw["ordered_link_occurrences"].extend({
            "ordinal": len(raw["ordered_link_occurrences"]),
            "argument_index": offset + len(target["ordered_inputs"]) + ordinal,
            "argument_count": 1, "kind": "system-argument",
            "reference_ordinal": ordinal,
        } for ordinal in range(len(arguments)))
        dependencies, _boundaries = project_link_external_dependencies(
            raw, target["target_id"],
        )
        authority = project_link_authority(
            raw, target["target_id"], target["ordered_inputs"], dependencies,
        )
        if authority is None:
            raise ValueError("test link authority is missing")
        target.update(authority)
        external_dependencies.extend(dependencies)
    return {"semantic_sha256": semantic, "translation_units": units,
            "targets": [*objects, *products], "toolchains": toolchains,
            "external_dependencies": external_dependencies}


def _scope(unit_id, reachable, terminal, index=0, count=1):
    record = {"unit_id": unit_id, "variant": {"key": unit_id, "index": index,
                                               "count": count},
              "object_owner_target_id": f"obj-{unit_id}",
              "reachable_target_ids": sorted(reachable),
              "terminal_target_ids": sorted(terminal)}
    status = "object-only-conservative" if not reachable else "target-bound"
    payload = {"schema_version": 1, "scope_kind": "scc-build-target-scope",
               "source_unit_ids": [unit_id], "unit_scopes": [record],
               "object_target_ids": [f"obj-{unit_id}"],
               "reachable_target_ids": sorted(reachable),
               "terminal_target_ids": sorted(terminal),
               "shared_reachable_target_ids": sorted(reachable),
               "domain_status": status}
    return {**payload, "scope_sha256": content_sha256(payload)}


def _candidate(unit_id, sha=None):
    sha = sha or content_sha256({"candidate": unit_id})
    return {"unit_id": unit_id, "artifact_id": f"candidate-{unit_id}",
            "source": _ref(f"candidates/{unit_id}.rs", sha)}


def _ref(path, sha):
    return {"path": path, "sha256": sha, "size_bytes": 1}


def _codes(topology):
    return {item["code"] for item in topology["topology_blockers"]}


__all__ = [
    "ARTIFACT", "SEMANTIC", "_build", "_candidate", "_codes", "_derive",
    "_product", "_ref", "_scope", "_unit",
]
