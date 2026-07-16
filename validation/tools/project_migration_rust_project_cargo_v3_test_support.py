from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from validation.tools.project_migration_build_ir_host_test_support import (
    BuildIRHostBindingTestCase,
)
from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.build_ir import finalize_build_ir
from validation.tools._project_migration_harness.build_ir_projection import target_closure
from validation.tools._project_migration_harness.migration_target_scope import (
    derive_build_ir_target_scopes,
)
from validation.tools._project_migration_harness.rust_candidate_facts import (
    derive_rust_metadata,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_derivation import (
    derive_rust_project_ir_v3_from_candidates,
)
from validation.tools._project_migration_harness.rust_project_ir_records import (
    public_records,
)
from validation.tools._project_migration_harness.rust_project_ir_source_facts import (
    derive_bound_candidate_source_facts,
)
from validation.tools._project_migration_harness.rust_project_ir_v3 import (
    build_rust_project_ir_v3,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_validation import (
    module_id_for_target_candidate,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_topology_products import (
    input_occurrence_id,
)


class V3CargoFixture:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.host = BuildIRHostBindingTestCase(methodName="runTest")
        self.host.setUp()
        self.manifest: dict | None = None
        self.dag_ref: dict | None = None
        self.descriptor: dict | None = None

    def close(self) -> None:
        self.host.doCleanups()

    def build(
        self, source: str, *, product: str = "archive",
        link_arguments: tuple[str, ...] = (),
    ) -> dict:
        if product not in {"archive", "link"}:
            raise ValueError("unsupported fixture product")
        build_ir = copy.deepcopy(self.host.standard_build_ir())
        build_ir["targets"] = [
            item for item in build_ir["targets"]
            if item["kind"] in {"object", product}
        ]
        if product == "link":
            for target in build_ir["targets"]:
                if target["kind"] == "link":
                    target["ordered_link_arguments"] = list(link_arguments)
        build_ir["external_dependencies"] = []
        build_ir["target_closure"] = target_closure(build_ir["targets"])
        build_ir = finalize_build_ir(build_ir)
        build_ref = write_json_artifact(
            self.root, f"plan/{product}-build-ir.json", build_ir,
        )
        source_unit_id = str(build_ir["translation_units"][0]["unit_id"])
        group_id = "group-a"
        scope = derive_build_ir_target_scopes(
            [build_ir], {group_id: [source_unit_id]},
        )[group_id]
        graph = {
            "schema_version": 1, "status": "ready",
            "sccs": [{
                "scc_id": group_id, "dependency_scc_ids": [],
                "source_unit_ids": [source_unit_id], "target_scope": scope,
            }],
            "waves": [{"wave_index": 0, "scc_ids": [group_id]}],
        }
        graph_ref = write_json_artifact(
            self.root, f"plan/{product}-migration-graph.json", graph,
        )
        placeholder = {
            "path": "plan/placeholder.json", "sha256": "f" * 64,
            "size_bytes": 1,
        }
        manifest = {
            "schema_version": 1, "profile": "competition",
            "dag": {group_id: []},
            "dag_order": [group_id],
            "build_ir": {
                "status": "bound", "artifact": build_ref,
                "verification": placeholder, "worker_admission": placeholder,
            },
            "migration_graph": graph_ref,
            "target_scopes": {group_id: {
                "group_content_sha256": "e" * 64,
                "scope_sha256": scope["scope_sha256"],
            }},
            "claim_boundary": {
                "semantic_gate": False, "translation_coverage_numerator": 0,
            },
        }
        dag_ref = write_json_artifact(
            self.root, f"plan/{product}-integration-manifest.json", manifest,
        )
        raw = source.encode("utf-8")
        source_path = self.root / f"candidates/{product}.rs"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(raw)
        descriptor = {
            "unit_id": group_id, "group_id": group_id,
            "artifact_id": f"candidate-{product}", "status": "accepted",
            "source_path": f"candidates/{product}.rs",
            "sha256": hashlib.sha256(raw).hexdigest(),
            **derive_rust_metadata(source),
        }
        self.manifest = manifest
        self.dag_ref = dag_ref
        self.descriptor = descriptor
        return derive_rust_project_ir_v3_from_candidates(
            migration_manifest=manifest, migration_dag_ref=dag_ref,
            build_ir_refs=[build_ref], candidate_descriptors=[descriptor],
            artifact_root=self.root,
        )


def direct_two_package_ir(
    *, second_package_executable: bool = False,
) -> tuple[dict, dict[str, bytes]]:
    sources = {
        "unit-bin": b"fn main() {}\n",
        "unit-lib": (
            b"fn main() { let _ = 1; }\n" if second_package_executable
            else b"pub fn value() -> i32 { 7 }\n"
        ),
    }
    shas = {key: hashlib.sha256(value).hexdigest() for key, value in sources.items()}
    builds = ["b" * 64]
    modules = {}
    for suffix in ("bin", "lib"):
        unit_id = f"unit-{suffix}"
        module_id = module_id_for_target_candidate(
            f"namespace-{suffix}", unit_id, shas[unit_id], [f"source-{suffix}"],
        )
        modules[suffix] = {
            "module_id": module_id, "package_id": f"package-{suffix}",
            "target_id": f"target-{suffix}",
            "target_namespace_id": f"namespace-{suffix}",
            "rust_path": f"packages/package-{suffix}/src/{module_id}.rs",
            "unit_id": unit_id, "source_unit_ids": [f"source-{suffix}"],
            "candidate_sha256": shas[unit_id], "visibility": "crate",
            "evidence": _evidence(builds, [unit_id], [shas[unit_id]]),
        }
    packages, targets = [], []
    products = [
        ("bin", "executable", "bin", ["bin"]),
        (
            "lib",
            "executable" if second_package_executable else "static-library",
            "bin" if second_package_executable else "lib",
            ["bin"] if second_package_executable else ["rlib", "staticlib"],
        ),
    ]
    for suffix, product, kind, crate_types in products:
        module_id = modules[suffix]["module_id"]
        evidence = modules[suffix]["evidence"]
        packages.append({
            "package_id": f"package-{suffix}", "name": f"package_{suffix}",
            "build_ir_target_id": f"build-target-{suffix}",
            "product_kind": product, "dependency_package_ids": [],
            "target_ids": [f"target-{suffix}"], "module_ids": [module_id],
            "evidence": evidence,
        })
        targets.append({
            "target_id": f"target-{suffix}", "package_id": f"package-{suffix}",
            "name": f"target_{suffix}", "kind": kind,
            "crate_types": crate_types,
            "build_ir_target_id": f"build-target-{suffix}",
            "module_ids": [module_id], "input_occurrences": [{
                "ordinal": 0,
                "occurrence_id": input_occurrence_id(
                    builds[0], f"build-target-{suffix}", 0,
                ),
                "role": "link-input", "dependency_target_id": None,
                "object_target_id": f"object-target-{suffix}",
                "source_unit_id": f"source-{suffix}",
                "module_id": module_id,
                "binding_sha256": hashlib.sha256(
                    f"binding-{suffix}".encode("ascii"),
                ).hexdigest(),
            }],
            "ordered_link_arguments": [], "evidence": evidence,
        })
    metadata = derive_rust_metadata(sources["unit-lib"].decode())
    facts = derive_bound_candidate_source_facts(
        sources["unit-lib"].decode(), metadata["public_symbols"],
    )
    public_api = public_records(
        modules["lib"]["module_id"], "unit-lib", shas["unit-lib"], builds,
        metadata["public_symbols"], facts,
    )
    refs = [{
        "unit_id": unit_id, "artifact_id": f"candidate-{unit_id}",
        "source": {
            "path": f"candidates/{unit_id}.rs", "sha256": shas[unit_id],
            "size_bytes": len(sources[unit_id]),
        },
    } for unit_id in sorted(sources)]
    ref = lambda path, sha: {"path": path, "sha256": sha, "size_bytes": 1}
    ir = build_rust_project_ir_v3(
        migration_dag_ref=ref("plan/dag.json", "a" * 64),
        migration_graph_ref=ref("plan/graph.json", "c" * 64),
        build_ir_refs=[ref("plan/build.json", builds[0])],
        candidate_refs=refs,
        workspace={
            "workspace_id": "workspace-two", "resolver": "2",
            "package_ids": ["package-bin", "package-lib"],
            "default_package_ids": ["package-bin", "package-lib"],
            "evidence": _evidence(builds, sorted(sources), sorted(shas.values())),
        },
        packages=packages, targets=targets, modules=list(modules.values()),
        public_api=public_api,
    )
    return ir, sources


def _evidence(builds, units, candidates) -> dict[str, list[str]]:
    return {
        "build_ir_sha256s": sorted(builds), "dag_unit_ids": sorted(units),
        "candidate_sha256s": sorted(candidates),
    }


__all__ = ["V3CargoFixture", "direct_two_package_ir"]
