from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.build_ir import stable_build_id
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.project_repair_context import (
    build_project_repair_context,
)
from validation.tools._project_migration_harness.project_repair_patch import (
    apply_project_repair_operations,
)
from validation.tools._project_migration_harness.rust_project_ir import (
    build_rust_project_ir,
)
from validation.tools.project_migration_project_repair_test_support import (
    coordinated_case,
    sha,
)


class ProjectRepairPatchNativeLinkTests(unittest.TestCase):
    def test_preserves_bound_native_link_plan(self) -> None:
        base_ir, context, response = self._repair_case(with_plan=True)

        candidate = apply_project_repair_operations(base_ir, context, response)

        self.assertEqual(
            base_ir["native_link_requirements"],
            candidate["native_link_requirements"],
        )
        self.assertEqual(base_ir["native_link_plans"], candidate["native_link_plans"])
        self.assertEqual(1, len(candidate["native_link_plans"]))
        self._assert_candidate_only(candidate)

    def test_preserves_native_link_requirements_with_empty_plan(self) -> None:
        base_ir, context, response = self._repair_case(with_plan=False)

        candidate = apply_project_repair_operations(base_ir, context, response)

        self.assertEqual(
            base_ir["native_link_requirements"],
            candidate["native_link_requirements"],
        )
        self.assertEqual([], base_ir["native_link_plans"])
        self.assertEqual([], candidate["native_link_plans"])
        self._assert_candidate_only(candidate)

    def _repair_case(self, *, with_plan: bool) -> tuple[dict, dict, dict]:
        label = "native-link-plan" if with_plan else "native-link-empty-plan"
        seed_ir, _receipt = coordinated_case(label)
        requirement_identity = {
            "portable_name": "repair_native",
            "library_format": "static-archive",
        }
        requirement = {
            "requirement_id": stable_build_id(
                "native-link-requirement", requirement_identity,
            ),
            **requirement_identity,
            "dependency_count": 1,
            "dependency_set_sha256": sha(f"dependencies:{label}"),
            "consumer_target_count": 1,
            "consumer_target_set_sha256": sha(f"consumers:{label}"),
        }
        plans = []
        if with_plan:
            plans.append({
                "requirement_id": requirement["requirement_id"],
                "strategy": "rustc-link-lib",
                "rustc_link_name": requirement["portable_name"],
                "rustc_link_kind": "static",
                "candidate_sha256": seed_ir["bindings"]["candidates"][0][
                    "source"
                ]["sha256"],
            })
        sections = {
            name: seed_ir[name]
            for name in (
                "modules", "public_api", "shared_types", "global_ownership",
                "initialization", "ffi_boundaries", "cfgs", "features",
                "unsafe_obligations",
            )
        }
        base_ir = build_rust_project_ir(
            migration_dag_ref=seed_ir["bindings"]["migration_dag"],
            build_ir_refs=seed_ir["bindings"]["build_ir"],
            candidate_refs=seed_ir["bindings"]["candidates"],
            crate=seed_ir["crate"],
            native_link_requirements=[requirement],
            native_link_plans=plans,
            **sections,
        )
        receipt = coordinate_project_interfaces(base_ir)
        repair_item = receipt["project_repair_queue"]["items"][0]
        context = build_project_repair_context(
            base_ir,
            receipt,
            receipt_epoch=1,
            repair_id=repair_item["repair_id"],
        )
        public_api_ids = {
            item["declaration_id"] for item in context["visible_records"]["public_api"]
        }
        record_id = next(
            item for item in context["diagnostic"]["entity_ids"]
            if item in public_api_ids
        )
        response = {
            "base_rust_project_ir_sha256": base_ir["ir_sha256"],
            "context_sha256": context["context_sha256"],
            "operations": [{
                "section": "public_api",
                "action": "replace",
                "record_id": record_id,
                "changes": {"symbol": "repaired_symbol"},
            }],
        }
        return base_ir, context, response

    def _assert_candidate_only(self, candidate: dict) -> None:
        self.assertEqual({
            "artifact_role": "rust-project-ir-candidate",
            "semantic_gate": False,
            "semantic_pass": False,
            "translation_coverage_numerator": 0,
        }, candidate["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
