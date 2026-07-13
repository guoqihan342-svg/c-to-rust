from __future__ import annotations

import unittest
from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_interface_coordinator import (
    COORDINATOR_RECEIPT_SHA256_FIELD,
    PROJECT_REPAIR_QUEUE_SHA256_FIELD,
    coordinate_project_interfaces,
    coordinator_receipt_projection,
    project_repair_queue_projection,
)
from validation.tools._project_migration_harness.rust_project_ir import (
    build_rust_project_ir,
)
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    VIRTUAL_CRATE_ROOT_MODULE_ID,
)
from validation.tools.test_project_migration_rust_project_ir import (
    _base_input,
    _evidence,
    _sha,
)
def _record_evidence(values: dict, module: dict) -> dict[str, object]:
    return _evidence(
        values["build_ir_refs"][0]["sha256"],
        module["unit_id"],
        module["candidate_sha256"],
    )
def _record_pair(values: dict, section: str, conflict: bool) -> list[dict]:
    left, right = values["modules"]
    second = right if conflict else left
    left_evidence = _record_evidence(values, left)
    second_evidence = _record_evidence(values, second)
    if section == "public_api":
        return [
            {"declaration_id": "api-a", "module_id": left["module_id"],
             "symbol": "probe", "kind": "function", "signature": "fn()->i32",
             "visibility": "public", "evidence": left_evidence},
            {"declaration_id": "api-b", "module_id": second["module_id"],
             "symbol": "probe", "kind": "function",
             "signature": "fn()->u64" if conflict else "fn()->i32",
             "visibility": "public", "evidence": second_evidence},
        ]
    if section == "shared_types":
        return [
            {"declaration_id": "type-a", "module_id": left["module_id"],
             "name": "Probe", "kind": "struct", "layout_sha256": _sha("layout"),
             "repr": "C", "evidence": left_evidence},
            {"declaration_id": "type-b", "module_id": second["module_id"],
             "name": "Probe", "kind": "struct",
             "layout_sha256": _sha("other-layout" if conflict else "layout"),
             "repr": "C", "evidence": second_evidence},
        ]
    if section == "global_ownership":
        return [
            {"declaration_id": "global-a", "module_id": left["module_id"],
             "symbol": "PROBE", "access": "owned", "evidence": left_evidence},
            {"declaration_id": "global-b", "module_id": second["module_id"],
             "symbol": "PROBE", "access": "owned", "evidence": second_evidence},
        ]
    if section == "ffi_boundaries":
        return [
            {"declaration_id": "ffi-a", "module_id": left["module_id"],
             "symbol": "probe", "direction": "import", "abi": "C",
             "link_name": "probe", "evidence": left_evidence},
            {"declaration_id": "ffi-b", "module_id": second["module_id"],
             "symbol": "probe", "direction": "import",
             "abi": "system" if conflict else "C", "link_name": "probe",
             "evidence": second_evidence},
        ]
    if section == "features":
        return [
            {"feature_id": "feature-a", "name": "probe", "default": False,
             "enables": [], "module_ids": [left["module_id"]],
             "evidence": left_evidence},
            {"feature_id": "feature-b", "name": "probe", "default": conflict,
             "enables": [], "module_ids": [second["module_id"]],
             "evidence": second_evidence},
        ]
    if section == "cfgs":
        return [
            {"cfg_id": "cfg-a", "expression": "probe",
             "module_ids": [left["module_id"]], "evidence": left_evidence},
            {"cfg_id": "cfg-b", "expression": "probe",
             "module_ids": [second["module_id"]], "evidence": second_evidence},
        ]
    return [
        {"init_id": "init-a", "module_id": left["module_id"],
         "function": "probe_init", "phase": "startup", "after": [],
         "evidence": left_evidence},
        {"init_id": "init-b", "module_id": second["module_id"],
         "function": "probe_init", "phase": "shutdown" if conflict else "startup",
         "after": [], "evidence": second_evidence},
    ]


class ProjectInterfaceCoordinatorHardeningTests(unittest.TestCase):
    def test_virtual_and_candidate_roots_are_both_reachable(self) -> None:
        candidate = coordinate_project_interfaces(
            build_rust_project_ir(**_base_input())
        )
        values = _base_input()
        values["crate"]["root_module_id"] = VIRTUAL_CRATE_ROOT_MODULE_ID
        for module in values["modules"]:
            module["parent_module_id"] = None
        virtual = coordinate_project_interfaces(build_rust_project_ir(**values))
        self.assertEqual("candidate-ready", candidate["status"])
        self.assertEqual("candidate-ready", virtual["status"])
        self.assertEqual([], virtual["diagnostics"])

    def test_unknown_parent_cycle_and_orphans_are_diagnosed(self) -> None:
        values = _base_input()
        values["crate"]["root_module_id"] = VIRTUAL_CRATE_ROOT_MODULE_ID
        values["modules"][0]["parent_module_id"] = values["modules"][1]["module_id"]
        values["modules"][1]["parent_module_id"] = values["modules"][0]["module_id"]
        result = coordinate_project_interfaces(build_rust_project_ir(**values))
        codes = [item["code"] for item in result["diagnostics"]]
        self.assertIn("cyclic_module_parent", codes)
        self.assertEqual(2, codes.count("orphan_module"))

        values = _base_input()
        values["crate"]["root_module_id"] = VIRTUAL_CRATE_ROOT_MODULE_ID
        values["modules"][0]["parent_module_id"] = None
        values["modules"][1]["parent_module_id"] = "missing-parent"
        result = coordinate_project_interfaces(build_rust_project_ir(**values))
        codes = [item["code"] for item in result["diagnostics"]]
        self.assertIn("unknown_parent_module", codes)
        self.assertEqual(1, codes.count("orphan_module"))

    def test_every_section_rejects_unknown_module_references(self) -> None:
        values = _base_input()
        left = values["modules"][0]
        evidence = _record_evidence(values, left)
        unknown = "missing-module"
        values["public_api"].append({
            "declaration_id": "api-missing", "module_id": unknown,
            "symbol": "missing_api", "kind": "function", "signature": "fn()",
            "visibility": "public", "evidence": evidence,
        })
        values["shared_types"] = [{
            "declaration_id": "type-missing", "module_id": unknown, "name": "Missing",
            "kind": "struct", "layout_sha256": _sha("missing-layout"), "repr": "C",
            "evidence": evidence,
        }]
        values["global_ownership"] = [{
            "declaration_id": "global-missing", "module_id": unknown,
            "symbol": "MISSING", "access": "owned", "evidence": evidence,
        }]
        values["initialization"] = [{
            "init_id": "init-missing", "module_id": unknown, "function": "init_missing",
            "phase": "startup", "after": [], "evidence": evidence,
        }]
        values["ffi_boundaries"] = [{
            "declaration_id": "ffi-missing", "module_id": unknown, "symbol": "missing",
            "direction": "import", "abi": "C", "link_name": "missing",
            "evidence": evidence,
        }]
        values["cfgs"] = [{
            "cfg_id": "cfg-missing", "expression": "missing",
            "module_ids": [unknown], "evidence": evidence,
        }]
        values["features"] = [{
            "feature_id": "feature-missing", "name": "missing", "default": False,
            "enables": [], "module_ids": [unknown], "evidence": evidence,
        }]
        values["unsafe_obligations"].append({
            "obligation_id": "unsafe-missing", "module_id": unknown,
            "kind": "raw-pointer-read", "reason_code": "missing-owner",
            "source_span": None, "evidence": evidence,
        })
        receipt = coordinate_project_interfaces(build_rust_project_ir(**values))
        codes = {item["code"] for item in receipt["diagnostics"]}
        self.assertEqual({
            "public_api_references_unknown_module",
            "shared_type_references_unknown_module",
            "global_ownership_references_unknown_module",
            "initialization_references_unknown_module",
            "ffi_boundary_references_unknown_module",
            "cfg_references_unknown_module",
            "feature_references_unknown_module",
            "unsafe_obligation_references_unknown_module",
        }, codes)
        self.assertTrue(receipt["project_repair_queue"]["items"])
        for item in receipt["project_repair_queue"]["items"]:
            self.assertEqual([unknown], item["unresolved_module_ids"])
            self.assertEqual([], item["affected_unit_ids"])

    def test_duplicate_and_conflicting_interface_classes_are_generic(self) -> None:
        expected = {
            "public_api": ("duplicate_public_symbol", "conflicting_public_api"),
            "shared_types": (
                "duplicate_shared_type_definition", "conflicting_shared_type",
            ),
            "global_ownership": (
                "duplicate_global_owner", "conflicting_global_ownership",
            ),
            "ffi_boundaries": ("duplicate_ffi_boundary", "conflicting_ffi_boundary"),
            "features": ("duplicate_feature", "conflicting_feature"),
            "cfgs": ("duplicate_cfg", "conflicting_cfg"),
            "initialization": (
                "duplicate_initialization", "conflicting_initialization",
            ),
        }
        for section, codes in expected.items():
            for conflict, code in zip((False, True), codes):
                with self.subTest(section=section, conflict=conflict):
                    values = _base_input()
                    values[section] = _record_pair(values, section, conflict)
                    diagnostics = coordinate_project_interfaces(
                        build_rust_project_ir(**values)
                    )["diagnostics"]
                    self.assertIn(code, {item["code"] for item in diagnostics})
        values = _base_input()
        records = _record_pair(values, "public_api", False)
        conflicting = _record_pair(values, "public_api", True)[1]
        conflicting["declaration_id"] = "api-c"
        values["public_api"] = [*records, conflicting]
        codes = {
            item["code"] for item in coordinate_project_interfaces(
                build_rust_project_ir(**values)
            )["diagnostics"]
        }
        self.assertTrue({"duplicate_public_symbol", "conflicting_public_api"} <= codes)

    def test_distinct_rust_symbols_cannot_claim_one_native_link_name(self) -> None:
        values = _base_input()
        left, right = values["modules"]
        values["ffi_boundaries"] = [
            {"declaration_id": "ffi-left", "module_id": left["module_id"],
             "symbol": "left_binding", "direction": "export", "abi": "C",
             "link_name": "native_entry",
             "evidence": _record_evidence(values, left)},
            {"declaration_id": "ffi-right", "module_id": right["module_id"],
             "symbol": "right_binding", "direction": "export", "abi": "C",
             "link_name": "native_entry",
             "evidence": _record_evidence(values, right)},
        ]

        result = coordinate_project_interfaces(build_rust_project_ir(**values))

        self.assertIn(
            "conflicting_ffi_boundary",
            {item["code"] for item in result["diagnostics"]},
        )

    def test_receipt_queue_and_repairs_bind_canonical_inputs(self) -> None:
        values = _base_input()
        values["public_api"] = _record_pair(values, "public_api", True)
        ir = build_rust_project_ir(**values)
        receipt = coordinate_project_interfaces(ir)
        queue = receipt["project_repair_queue"]
        self.assertEqual(ir["ir_sha256"], receipt["rust_project_ir_sha256"])
        self.assertEqual(
            ir["interface_sha256"], receipt["rust_project_interface_sha256"]
        )
        self.assertEqual(ir["ir_sha256"], queue["rust_project_ir_sha256"])
        self.assertEqual(
            ir["interface_sha256"], queue["rust_project_interface_sha256"]
        )
        self.assertEqual(
            receipt[COORDINATOR_RECEIPT_SHA256_FIELD],
            content_sha256(coordinator_receipt_projection(receipt)),
        )
        self.assertEqual(
            queue[PROJECT_REPAIR_QUEUE_SHA256_FIELD],
            content_sha256(project_repair_queue_projection(queue)),
        )
        receipt_drift = coordinator_receipt_projection(receipt)
        receipt_drift["status"] = "candidate-ready"
        self.assertNotEqual(
            receipt[COORDINATOR_RECEIPT_SHA256_FIELD], content_sha256(receipt_drift)
        )
        queue_drift = project_repair_queue_projection(queue)
        queue_drift["max_items"] += 1
        self.assertNotEqual(
            queue[PROJECT_REPAIR_QUEUE_SHA256_FIELD], content_sha256(queue_drift)
        )
        diagnostic_hashes = {item["diagnostic_sha256"] for item in receipt["diagnostics"]}
        for diagnostic in receipt["diagnostics"]:
            projection = {
                key: item for key, item in diagnostic.items()
                if key != "diagnostic_sha256"
            }
            self.assertEqual(
                diagnostic["diagnostic_sha256"], content_sha256(projection)
            )
        for item in queue["items"]:
            self.assertEqual(ir["ir_sha256"], item["rust_project_ir_sha256"])
            self.assertEqual(
                ir["interface_sha256"], item["rust_project_interface_sha256"]
            )
            self.assertIn(item["diagnostic_sha256"], diagnostic_hashes)
            self.assertEqual([], item["unresolved_module_ids"])
            self.assertTrue(item["candidate_only"])
        self.assertFalse(receipt["claim_boundary"]["semantic_gate"])
        self.assertFalse(receipt["claim_boundary"]["semantic_pass"])


if __name__ == "__main__":
    unittest.main()
