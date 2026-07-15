from __future__ import annotations

import copy
import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_symbol_context import (
    build_native_symbol_context,
    model_native_symbol_context,
    validate_native_symbol_context,
)
from validation.tools.project_migration_native_symbol_test_support import (
    NativeSymbolTestCase,
)


class NativeSymbolContextTests(NativeSymbolTestCase):
    def test_groups_imports_and_excludes_export_only_boundaries(self) -> None:
        self.assertEqual("planning-required", self.symbol_context["status"])
        self.assertEqual(3, self.symbol_context["symbol_count"])
        self.assertEqual(2, self.symbol_context["provider_count"])
        by_name = {
            item["link_name"]: item for item in self.symbol_context["symbols"]
        }
        self.assertEqual(2, by_name["alpha_open"]["declaration_count"])
        self.assertEqual(1, by_name["beta_process"]["declaration_count"])
        self.assertEqual(1, by_name["runtime_alloc"]["declaration_count"])
        self.assertNotIn("project_export", by_name)
        self.assertEqual(
            self.rust_ir["ir_sha256"],
            self.symbol_context["bindings"]["rust_project_ir_sha256"],
        )

    def test_model_projection_is_path_free_and_omits_declaration_identity(self) -> None:
        projection = model_native_symbol_context(self.symbol_context)
        serialized = json.dumps(projection, sort_keys=True)
        self.assertNotIn("/private", serialized)
        self.assertNotIn("/different", serialized)
        self.assertNotIn("ffi-alpha-a", serialized)
        self.assertNotIn("ffi-alpha-b", serialized)
        self.assertNotIn("project_export", serialized)
        self.assertFalse(
            self.symbol_context["claim_boundary"]["symbol_assignments_resolved"],
        )
        self.assertFalse(self.symbol_context["claim_boundary"]["semantic_gate"])

    def test_context_reopens_all_three_inputs_and_rejects_tampering(self) -> None:
        self.assertEqual(
            self.symbol_context,
            validate_native_symbol_context(
                self.symbol_context,
                self.rust_ir,
                self.link_context,
                self.link_candidate,
            ),
        )
        tampered = copy.deepcopy(self.symbol_context)
        tampered["symbols"][0]["declaration_count"] += 1
        with self.assertRaisesRegex(ValueError, "sha256_drift"):
            validate_native_symbol_context(tampered)

        rebound = copy.deepcopy(self.symbol_context)
        rebound["bindings"]["rust_project_ir_sha256"] = content_sha256("other")
        rebound["context_sha256"] = content_sha256({
            key: item for key, item in rebound.items() if key != "context_sha256"
        })
        with self.assertRaisesRegex(ValueError, "input_drift"):
            validate_native_symbol_context(
                rebound, self.rust_ir, self.link_context, self.link_candidate,
            )

    def test_canonical_order_is_independent_of_ffi_record_order(self) -> None:
        reversed_ir = self._rust_ir(list(reversed(self._ffi_boundaries())))
        rebuilt = build_native_symbol_context(
            reversed_ir, self.link_context, self.link_candidate,
        )
        self.assertEqual(self.symbol_context, rebuilt)

    def test_export_only_ir_needs_no_symbol_model_and_bad_direction_blocks(self) -> None:
        exported = [{
            "declaration_id": "ffi-only-export", "symbol": "rust_export",
            "direction": "export", "abi": "C", "link_name": "only_export",
        }]
        no_imports = build_native_symbol_context(
            self._rust_ir(exported), self.link_context, self.link_candidate,
        )
        self.assertEqual("not-required", no_imports["status"])
        self.assertEqual([], no_imports["symbols"])

        invalid = copy.deepcopy(exported)
        invalid[0]["direction"] = "sideways"
        with self.assertRaisesRegex(ValueError, "ffi_direction_invalid"):
            build_native_symbol_context(
                self._rust_ir(invalid), self.link_context, self.link_candidate,
            )


if __name__ == "__main__":
    unittest.main()
