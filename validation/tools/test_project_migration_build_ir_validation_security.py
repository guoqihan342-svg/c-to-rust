from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.build_ir import (
    finalize_build_ir,
    target_record,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    BuildIRValidationError,
    validate_build_ir,
)
from validation.tools.project_migration_rust_project_test_support import valid_build_ir


# These assertions intentionally precede the parent thread's validator change.
# Keep them active so the missing fail-closed behavior remains visible.
class ProjectMigrationBuildIRValidationSecurityTests(unittest.TestCase):
    """Parent-thread contracts; expected to fail until the validator enforces them."""

    def test_claim_boundary_cannot_assert_semantic_authority(self) -> None:
        for field, asserted in (
            ("semantic_gate", True),
            ("translation_coverage_numerator", 1),
        ):
            build_ir = valid_build_ir()
            build_ir["claim_boundary"][field] = asserted
            build_ir = finalize_build_ir(build_ir)
            with self.subTest(field=field), self.assertRaises(BuildIRValidationError):
                validate_build_ir(build_ir)

    def test_translation_unit_toolchain_id_must_resolve(self) -> None:
        build_ir = self._build_ir_with_known_toolchain()
        build_ir["translation_units"][0]["toolchain_id"] = "unknown-toolchain"
        build_ir = finalize_build_ir(build_ir)

        with self.assertRaises(BuildIRValidationError):
            validate_build_ir(build_ir)

    def test_abi_toolchain_id_must_resolve(self) -> None:
        build_ir = self._build_ir_with_known_toolchain()
        build_ir["abi_facts"][0]["toolchain_id"] = "unknown-toolchain"
        build_ir = finalize_build_ir(build_ir)

        with self.assertRaises(BuildIRValidationError):
            validate_build_ir(build_ir)

    def test_target_toolchain_id_must_resolve_when_present(self) -> None:
        build_ir = self._build_ir_with_known_toolchain()
        target = target_record(
            "object-target",
            "build/input.o",
            "object",
            [],
            [],
            [],
            [],
            [],
            {"raw_fact_role": "discovery"},
        )
        target["toolchain_id"] = "unknown-toolchain"
        build_ir["targets"] = [target]
        build_ir["target_closure"] = ["object-target"]
        build_ir = finalize_build_ir(build_ir)

        with self.assertRaises(BuildIRValidationError):
            validate_build_ir(build_ir)

    @staticmethod
    def _build_ir_with_known_toolchain() -> dict:
        build_ir = valid_build_ir()
        provenance = {"raw_fact_role": "discovery"}
        build_ir["toolchains"] = [{
            "toolchain_id": "known-toolchain",
            "driver": "clang",
            "wrappers": [],
            "language": "c",
            "identity": "compile-database-driver-token",
            "provenance": provenance,
        }]
        build_ir["translation_units"][0]["toolchain_id"] = "known-toolchain"
        build_ir["abi_facts"][0]["toolchain_id"] = "known-toolchain"
        return finalize_build_ir(build_ir)


if __name__ == "__main__":
    unittest.main()
