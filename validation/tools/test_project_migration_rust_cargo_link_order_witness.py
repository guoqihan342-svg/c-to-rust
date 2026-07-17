from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.cargo_compiler_artifact_evidence import (
    parse_cargo_compiler_artifact_evidence,
)
from validation.tools._project_migration_harness.rust_cargo_link_order_witness import (
    build_rust_cargo_link_order_witness,
)
from validation.tools._project_migration_harness.rust_cargo_target_link_trace import (
    parse_rust_cargo_target_link_trace,
)
from validation.tools.project_migration_rust_cargo_link_order_test_support import (
    cargo_stream,
    path_sha256,
    rust_products,
    rust_project_ir,
)


class RustCargoLinkOrderWitnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ir = rust_project_ir()
        self.products = rust_products()

    def witness(self, raw: bytes) -> dict:
        return build_rust_cargo_link_order_witness(
            self.ir,
            parse_cargo_compiler_artifact_evidence(raw),
            self.products,
            parse_rust_cargo_target_link_trace(raw),
        )

    def test_matching_dependency_artifact_order_is_ready(self) -> None:
        result = self.witness(cargo_stream())

        self.assertEqual("ready", result["status"])
        self.assertEqual("required", result["mode"])
        self.assertTrue(result["coverage"]["link_order_coverage_complete"])
        self.assertEqual([0, 1], [
            item["first_link_ordinal"]
            for item in result["targets"][0]["dependencies"]
        ])
        self.assertEqual(
            [path_sha256("alpha"), path_sha256("beta")],
            [
                item["guest_path_sha256"]
                for item in result["targets"][0]["dependencies"]
            ],
        )

    def test_reverse_dependency_order_fails_closed(self) -> None:
        result = self.witness(cargo_stream(
            diagnostics=(("app", ("beta", "alpha")),),
        ))

        self.assertEqual("blocked", result["status"])
        self.assertIn(
            "rust_cargo_link_dependency_order_mismatch", _codes(result),
        )

    def test_missing_and_masquerading_target_traces_fail_closed(self) -> None:
        raw = cargo_stream()
        missing = build_rust_cargo_link_order_witness(
            self.ir, parse_cargo_compiler_artifact_evidence(raw),
            self.products, None,
        )
        self.assertIn("rust_cargo_target_link_trace_missing", _codes(missing))

        masquerading_raw = cargo_stream(
            diagnostics=(("gamma", ("alpha", "beta")),),
        )
        masquerading = self.witness(masquerading_raw)
        self.assertEqual("blocked", masquerading["status"])
        self.assertEqual({
            "rust_cargo_link_target_missing",
            "rust_cargo_link_target_undeclared",
        }, _codes(masquerading))

    def test_staticlib_without_target_trace_is_ready_not_required(self) -> None:
        raw = cargo_stream(static_only=True)
        result = build_rust_cargo_link_order_witness(
            rust_project_ir(static_only=True),
            parse_cargo_compiler_artifact_evidence(raw),
            rust_products(static_only=True),
            None,
        )

        self.assertEqual("ready", result["status"])
        self.assertEqual("not-required", result["mode"])
        self.assertEqual([], result["targets"])

    def test_extra_workspace_dependency_artifact_fails_closed(self) -> None:
        result = self.witness(cargo_stream(
            diagnostics=(("app", ("alpha", "gamma", "beta")),),
        ))

        self.assertEqual("blocked", result["status"])
        self.assertIn(
            "rust_cargo_link_dependency_unexpected", _codes(result),
        )

    def test_repeated_dependency_artifact_fails_exact_count_check(self) -> None:
        result = self.witness(cargo_stream(
            diagnostics=(("app", ("alpha", "alpha", "beta")),),
        ))

        self.assertEqual("blocked", result["status"])
        self.assertIn(
            "rust_cargo_link_dependency_occurrence_count_mismatch", _codes(result),
        )

    def test_trace_and_compiler_sources_must_be_the_same_capture(self) -> None:
        compiler_source = cargo_stream()
        trace_source = cargo_stream(noise="untrusted source drift")
        result = build_rust_cargo_link_order_witness(
            self.ir,
            parse_cargo_compiler_artifact_evidence(compiler_source),
            self.products,
            parse_rust_cargo_target_link_trace(trace_source),
        )

        self.assertEqual("blocked", result["status"])
        self.assertTrue(any("source" in code for code in _codes(result)))


def _codes(value: dict) -> set[str]:
    return {item["code"] for item in value["blockers"]}


if __name__ == "__main__":
    unittest.main()
