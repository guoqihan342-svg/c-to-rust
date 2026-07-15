from __future__ import annotations

import copy
import hashlib
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.rust_project_ir_v3 import (
    build_rust_project_ir_v3,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_validation import (
    RUST_PROJECT_IR_V3_SCHEMA_VERSION,
    interface_projection_v3,
    module_id_for_target_candidate,
    validate_rust_project_ir_v3,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _ref(label: str, path: str) -> dict[str, object]:
    return {"path": path, "sha256": _sha(label), "size_bytes": len(label)}


def _evidence(build: str, units: list[str], candidates: list[str]) -> dict[str, object]:
    return {
        "build_ir_sha256s": [build], "dag_unit_ids": sorted(set(units)),
        "candidate_sha256s": sorted(set(candidates)),
    }


def _payload(
    *, duplicate_candidate: bool = False,
    occurrences: list[dict[str, object]] | None = None,
    blockers: list[dict[str, str]] | None = None,
) -> dict:
    build = _ref("build", "facts/build-ir.json")
    candidate_sha = _sha("same-candidate")
    units = ["scc-a", "scc-b"] if duplicate_candidate else ["scc-a"]
    target_ids = ["target-a", "target-b"] if duplicate_candidate else ["target-a"]
    candidates = [{
        "unit_id": unit, "artifact_id": f"candidate-{unit}",
        "source": {"path": "candidates/shared.rs", "sha256": candidate_sha,
                   "size_bytes": 17},
    } for unit in units]
    modules = []
    targets = []
    for index, (unit, target_id) in enumerate(zip(units, target_ids)):
        namespace = f"namespace-{index}"
        source_units = [f"variant-{index}"]
        module_id = module_id_for_target_candidate(
            namespace, unit, candidate_sha, source_units,
        )
        evidence = _evidence(str(build["sha256"]), [unit], [candidate_sha])
        modules.append({
            "module_id": module_id, "package_id": "package-a", "target_id": target_id,
            "target_namespace_id": namespace, "rust_path": f"src/{target_id}.rs",
            "unit_id": unit, "source_unit_ids": source_units,
            "candidate_sha256": candidate_sha, "visibility": "crate",
            "evidence": evidence,
        })
        targets.append({
            "target_id": target_id, "package_id": "package-a", "name": target_id,
            "kind": "lib", "crate_types": ["rlib"],
            "build_ir_target_id": f"build-{target_id}", "module_ids": [module_id],
            "input_occurrences": occurrences if index == 0 and occurrences else [],
            "ordered_link_arguments": [], "evidence": evidence,
        })
    module_ids = sorted(item["module_id"] for item in modules)
    all_evidence = _evidence(str(build["sha256"]), units, [candidate_sha])
    return build_rust_project_ir_v3(
        migration_dag_ref=_ref("dag", "facts/migration-dag.json"),
        migration_graph_ref=_ref("graph", "facts/migration-graph.json"),
        build_ir_refs=[build], candidate_refs=candidates,
        workspace={
            "workspace_id": "workspace-a", "resolver": "2",
            "package_ids": ["package-a"], "default_package_ids": ["package-a"],
            "evidence": all_evidence,
        },
        packages=[{
            "package_id": "package-a", "name": "package-a",
            "build_ir_target_id": "build-product-a", "product_kind": "static-library",
            "dependency_package_ids": [], "target_ids": target_ids,
            "module_ids": module_ids, "evidence": all_evidence,
        }],
        targets=targets, modules=modules, topology_blockers=blockers or [],
    )


def _rehash(payload: dict) -> None:
    payload["interface_sha256"] = content_sha256(interface_projection_v3(payload))
    payload.pop("ir_sha256", None)
    payload["ir_sha256"] = content_sha256(payload)


class RustProjectIRV3ValidationTests(unittest.TestCase):
    def test_valid_minimal_v3_and_strict_bindings(self) -> None:
        payload = _payload()
        self.assertEqual(3, RUST_PROJECT_IR_V3_SCHEMA_VERSION)
        self.assertNotIn("crate", payload)
        self.assertEqual(
            {"migration_dag", "migration_graph", "build_ir", "c_compilation_facts",
             "candidates"},
            set(payload["bindings"]),
        )
        self.assertEqual(
            payload["interface_sha256"], content_sha256(interface_projection_v3(payload)),
        )
        self.assertIsNone(validate_rust_project_ir_v3(payload))
        duplicate_build = copy.deepcopy(payload)
        duplicate = copy.deepcopy(duplicate_build["bindings"]["build_ir"][0])
        duplicate["path"] = "facts/z-build-ir.json"
        duplicate_build["bindings"]["build_ir"].append(duplicate)
        _rehash(duplicate_build)
        with self.assertRaisesRegex(ValueError, "BuildIR references"):
            validate_rust_project_ir_v3(duplicate_build)

    def test_equal_candidate_sha_is_valid_across_target_namespaces(self) -> None:
        payload = _payload(duplicate_candidate=True)
        left, right = payload["modules"]
        self.assertEqual(left["candidate_sha256"], right["candidate_sha256"])
        self.assertNotEqual(left["module_id"], right["module_id"])
        self.assertNotEqual(
            module_id_for_target_candidate("namespace-a", "scc", _sha("candidate"), ["u"]),
            module_id_for_target_candidate("namespace-b", "scc", _sha("candidate"), ["u"]),
        )
        validate_rust_project_ir_v3(payload)

    def test_wrong_content_derived_module_id_is_rejected(self) -> None:
        payload = _payload()
        old_id = payload["modules"][0]["module_id"]
        payload["modules"][0]["module_id"] = "module-wrong"
        payload["packages"][0]["module_ids"] = ["module-wrong"]
        payload["targets"][0]["module_ids"] = ["module-wrong"]
        self.assertNotEqual(old_id, "module-wrong")
        _rehash(payload)
        with self.assertRaisesRegex(ValueError, "module identity"):
            validate_rust_project_ir_v3(payload)

    def test_v2_shape_cannot_masquerade_as_v3(self) -> None:
        payload = _payload()
        payload["crate"] = {"crate_id": "legacy-single-crate"}
        for key in ("workspace", "packages", "targets", "topology_status",
                    "topology_blockers"):
            payload.pop(key)
        with self.assertRaisesRegex(ValueError, "top-level schema"):
            validate_rust_project_ir_v3(payload)

    def test_repeated_occurrences_preserve_ordinals_and_order(self) -> None:
        digest = _sha("same-input")
        occurrences = [{
            "ordinal": ordinal, "role": "archive-member", "dependency_target_id": None,
            "binding_sha256": digest,
        } for ordinal in range(2)]
        payload = _payload(occurrences=occurrences)
        self.assertEqual([0, 1], [item["ordinal"]
                                 for item in payload["targets"][0]["input_occurrences"]])
        validate_rust_project_ir_v3(payload)
        for label, mutate in (
            ("out-of-order", lambda items: items.reverse()),
            ("duplicate-ordinal", lambda items: items[1].update({"ordinal": 0})),
        ):
            with self.subTest(label=label):
                drifted = copy.deepcopy(payload)
                mutate(drifted["targets"][0]["input_occurrences"])
                _rehash(drifted)
                with self.assertRaisesRegex(ValueError, "occurrences are not canonical"):
                    validate_rust_project_ir_v3(drifted)

    def test_bidirectional_topology_drift_is_rejected(self) -> None:
        for label, mutate in (
            ("package-modules", lambda value: value["packages"][0].update({"module_ids": []})),
            ("target-modules", lambda value: value["targets"][0].update({"module_ids": []})),
            ("workspace-packages", lambda value: value["workspace"].update({"package_ids": []})),
        ):
            with self.subTest(label=label):
                payload = _payload()
                mutate(payload)
                _rehash(payload)
                with self.assertRaises(ValueError):
                    validate_rust_project_ir_v3(payload)

    def test_blocked_and_ready_constraints(self) -> None:
        blocker = {"code": "topology-unproven", "entity_kind": "target",
                   "entity_id": "target-a"}
        blocked = _payload(blockers=[blocker])
        self.assertEqual("blocked", blocked["topology_status"])
        validate_rust_project_ir_v3(blocked)
        ready_with_blocker = _payload()
        ready_with_blocker["topology_blockers"] = [blocker]
        _rehash(ready_with_blocker)
        blocked_without_blocker = _payload()
        blocked_without_blocker["topology_status"] = "blocked"
        _rehash(blocked_without_blocker)
        for payload in (ready_with_blocker, blocked_without_blocker):
            with self.assertRaisesRegex(ValueError, "status and blockers disagree"):
                validate_rust_project_ir_v3(payload)

    def test_object_only_blocked_topology_may_be_empty(self) -> None:
        payload = _payload()
        workspace_id = payload["workspace"]["workspace_id"]
        payload["workspace"]["package_ids"] = []
        payload["workspace"]["default_package_ids"] = []
        payload["packages"] = []
        payload["targets"] = []
        payload["modules"] = []
        payload["topology_status"] = "blocked"
        payload["topology_blockers"] = [{
            "code": "build_ir_object_only", "entity_kind": "workspace",
            "entity_id": workspace_id,
        }]
        _rehash(payload)
        validate_rust_project_ir_v3(payload)
        ready = copy.deepcopy(payload)
        ready["topology_status"] = "ready"
        ready["topology_blockers"] = []
        _rehash(ready)
        with self.assertRaisesRegex(ValueError, "package_ids|ready topology"):
            validate_rust_project_ir_v3(ready)

    def test_interface_and_ir_hash_drift_are_rejected(self) -> None:
        interface_drift = _payload()
        interface_drift["targets"][0]["name"] = "renamed"
        with self.assertRaisesRegex(ValueError, "interface hash drifted"):
            validate_rust_project_ir_v3(interface_drift)
        ir_drift = _payload()
        ir_drift["bindings"]["migration_graph"]["size_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "content hash drifted"):
            validate_rust_project_ir_v3(ir_drift)

    def test_claim_boundary_cannot_grant_semantic_credit(self) -> None:
        payload = _payload()
        payload["claim_boundary"]["semantic_pass"] = True
        _rehash(payload)
        with self.assertRaisesRegex(ValueError, "claim boundary"):
            validate_rust_project_ir_v3(payload)


if __name__ == "__main__":
    unittest.main()
