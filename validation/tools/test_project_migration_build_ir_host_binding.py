from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.build_ir import finalize_build_ir
from validation.tools._project_migration_harness.build_ir_host_toolchains import (
    HostToolchainProjection,
    validate_host_bound_toolchains,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    BuildIRValidationError,
    validate_build_ir,
)
from validation.tools._project_migration_harness.c_toolchain_probe import (
    ProbeExecution,
)
from validation.tools._project_migration_harness.c_toolchain_reopen import (
    C_TOOLCHAIN_RAW_ROLE,
)
from validation.tools._project_migration_harness.make_build_ir_projection import (
    MAKE_RAW_ROLE,
    project_make_build_ir,
)
from validation.tools.project_migration_build_ir_host_test_support import (
    BuildIRHostBindingTestCase,
    ContractToolchain,
    artifact_reference,
)


class ProjectMigrationBuildIRHostBindingTests(BuildIRHostBindingTestCase):
    def test_projection_emits_stable_canonical_role_records(self) -> None:
        evidence = self.full_evidence()

        first = HostToolchainProjection(evidence)
        first_ids = self._exercise_projection(first)
        records = first.records()
        validate_host_bound_toolchains(records)

        second = HostToolchainProjection(copy.deepcopy(evidence))
        second_ids = self._exercise_projection(second)
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(records, second.records())
        self.assertEqual(
            [item["toolchain_id"] for item in records],
            sorted({item["toolchain_id"] for item in records}),
        )

        by_id = {item["toolchain_id"]: item for item in records}
        compile_record = by_id[first_ids["compile"]]
        self.assertEqual(("gcc", ["distcc"], "compiler-driver"), (
            compile_record["driver"],
            compile_record["wrappers"],
            compile_record["role"],
        ))
        self.assertEqual(
            [("distcc", "wrapper"), ("gcc", "driver")],
            [(item["token"], item["relation"]) for item in compile_record["tools"]],
        )

        linker_driver = by_id[first_ids["linker-driver"]]
        self.assertEqual("linker-driver", linker_driver["role"])
        self.assertEqual(
            [("gcc", "driver"), ("ld", "derived-linker")],
            [(item["token"], item["relation"]) for item in linker_driver["tools"]],
        )
        for key, driver, role in (
            ("linker", "ld", "linker"),
            ("archiver", "ar", "archiver"),
            ("ranlib", "ranlib", "ranlib"),
        ):
            self.assertEqual((driver, role), (
                by_id[first_ids[key]]["driver"],
                by_id[first_ids[key]]["role"],
            ))
        self.assertTrue(all(
            item["provenance"] == {"raw_fact_role": C_TOOLCHAIN_RAW_ROLE}
            for item in records
        ))

    def test_projection_rejects_invalid_and_blocked_evidence(self) -> None:
        invalid = self.full_evidence()
        invalid["claim_boundary"]["semantic_gate"] = True
        with self.assertRaises(ValueError):
            HostToolchainProjection(invalid)

        blocked_fake = ContractToolchain(self.root / "blocked-tools")
        blocked_fake.special[("--version",)] = ProbeExecution(
            None, b"", b"", timed_out=True,
        )
        blocked = self.collect([
            {"token": "gcc", "roles": ["compiler-driver"]},
        ], blocked_fake)
        self.assertEqual("blocked", blocked["status"])
        with self.assertRaisesRegex(
            ValueError, "build_ir_c_toolchain_evidence_blocked",
        ):
            HostToolchainProjection(blocked)

    def test_normalized_build_facts_select_unique_absolute_evidence(self) -> None:
        compiler = str(self.fake.paths["gcc"])
        wrapper = str(self.fake.paths["distcc"])
        evidence = self.collect([
            {"token": compiler, "roles": ["compiler-driver"]},
            {"token": wrapper, "roles": ["compiler-wrapper"]},
        ])
        projection = HostToolchainProjection(evidence)

        identifier = projection.compile("gcc", ["distcc"], "c")
        record = {
            item["toolchain_id"]: item for item in projection.records()
        }[identifier]
        self.assertEqual(compiler, record["driver"])
        self.assertEqual([wrapper], record["wrappers"])

    def test_standard_projection_binds_units_abi_and_build_targets(self) -> None:
        build_ir = self.standard_build_ir()
        validate_build_ir(build_ir)

        identifiers = {
            item["toolchain_id"] for item in build_ir["toolchains"]
        }
        unit = build_ir["translation_units"][0]
        abi = build_ir["abi_facts"][0]
        self.assertEqual(unit["toolchain_id"], abi["toolchain_id"])
        self.assertIn(unit["toolchain_id"], identifiers)
        self.assertTrue(all(
            target["toolchain_id"] in identifiers
            for target in build_ir["targets"]
            if target["kind"] in {"object", "link", "archive"}
        ))

        records = {
            item["toolchain_id"]: item for item in build_ir["toolchains"]
        }
        targets = {item["kind"]: item for item in build_ir["targets"]}
        self.assertEqual(unit["toolchain_id"], targets["object"]["toolchain_id"])
        self.assertEqual(
            ("gcc", "linker-driver"),
            self._target_tool(targets["link"], records),
        )
        self.assertEqual(
            ("ar", "archiver"),
            self._target_tool(targets["archive"], records),
        )
        self.assertIn("derived-linker", {
            item["relation"]
            for item in records[targets["link"]["toolchain_id"]]["tools"]
        })
        self.assertEqual(
            sorted({
                "discovery",
                "generated-build-closure",
                "generated-build-closure-verification",
                C_TOOLCHAIN_RAW_ROLE,
            }),
            [item["role"] for item in build_ir["raw_fact_refs"]],
        )
        self.assertEqual(
            (True, "development", False, 0),
            self._claim_boundary(build_ir),
        )

    def test_make_projection_binds_all_command_tools_and_direct_linker(self) -> None:
        evidence = self.collect([
            {"token": "ar", "roles": ["archiver"]},
            {"token": "gcc", "roles": ["compiler-driver"]},
            {"token": "ld", "roles": ["linker"]},
            {"token": "ranlib", "roles": ["ranlib"]},
        ])
        report = self.make_report()
        build_ir = project_make_build_ir(
            self.project_root,
            report,
            artifact_reference("facts/make-report.json", report),
            max_units=8,
            toolchain_evidence=evidence,
            toolchain_reference=artifact_reference("facts/c-toolchain.json", evidence),
        )
        validate_build_ir(build_ir)

        records = {
            item["toolchain_id"]: item for item in build_ir["toolchains"]
        }
        self.assertEqual({
            ("gcc", "compiler-driver"),
            ("ar", "archiver"),
            ("ranlib", "ranlib"),
            ("ld", "linker"),
        }, {(item["driver"], item["role"]) for item in records.values()})
        self.assertNotIn(
            ("ld", "linker-driver"),
            {(item["driver"], item["role"]) for item in records.values()},
        )

        targets = {item["kind"]: item for item in build_ir["targets"]}
        self.assertEqual(
            ("gcc", "compiler-driver"),
            self._target_tool(targets["object"], records),
        )
        self.assertEqual(
            ("ar", "archiver"),
            self._target_tool(targets["archive"], records),
        )
        self.assertEqual(
            ("ld", "linker"),
            self._target_tool(targets["link"], records),
        )
        self.assertIn("ranlib", {
            item["kind"] for item in targets["archive"]["compile_argument_sets"]
        })
        self.assertEqual(
            sorted([C_TOOLCHAIN_RAW_ROLE, MAKE_RAW_ROLE]),
            [item["role"] for item in build_ir["raw_fact_refs"]],
        )
        self.assertEqual(
            (True, "development", False, 0),
            self._claim_boundary(build_ir),
        )

    def test_validator_rejects_missing_host_bound_target_foreign_keys(self) -> None:
        baseline = self.standard_build_ir()
        for kind in ("object", "link", "archive"):
            build_ir = copy.deepcopy(baseline)
            target = next(item for item in build_ir["targets"] if item["kind"] == kind)
            del target["toolchain_id"]
            build_ir = finalize_build_ir(build_ir)
            with self.subTest(kind=kind), self.assertRaisesRegex(
                BuildIRValidationError, "build_ir_toolchain_reference_invalid",
            ):
                validate_build_ir(build_ir)

    def test_validator_rejects_forged_host_toolchain_record(self) -> None:
        build_ir = self.standard_build_ir()
        build_ir["toolchains"][0]["driver"] = "forged-driver"
        build_ir = finalize_build_ir(build_ir)
        with self.assertRaisesRegex(
            BuildIRValidationError, "build_ir_host_toolchain_identity_invalid",
        ):
            validate_build_ir(build_ir)

    def test_validator_rejects_claim_boundary_raw_role_mismatch(self) -> None:
        baseline = self.standard_build_ir()
        raw_role_missing = copy.deepcopy(baseline)
        raw_role_missing["raw_fact_refs"] = [
            item for item in raw_role_missing["raw_fact_refs"]
            if item["role"] != C_TOOLCHAIN_RAW_ROLE
        ]
        boundary_false = copy.deepcopy(baseline)
        boundary_false["claim_boundary"]["host_toolchain_bound"] = False

        for label, build_ir in (
            ("raw-role-missing", raw_role_missing),
            ("boundary-false", boundary_false),
        ):
            with self.subTest(label=label), self.assertRaisesRegex(
                BuildIRValidationError, "build_ir_claim_boundary_invalid",
            ):
                validate_build_ir(finalize_build_ir(build_ir))


if __name__ == "__main__":
    unittest.main()
