from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import (
    write_json_artifact,
)
from validation.tools._project_migration_harness.build_ir import (
    BUILD_IR_SCHEMA_VERSION, LEGACY_BUILD_IR_EXTRACTOR,
    LEGACY_BUILD_IR_SCHEMA_VERSION, finalize_build_ir,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    BuildIRValidationError, validate_build_ir, verify_build_ir_artifact,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.make_build_ir_adapter import (
    materialize_selected_build_ir_stage,
)
from validation.tools.test_project_migration_make_support import MakeBundleFactory


class MakeBuildIRLegacyReopenTests(unittest.TestCase):
    def test_forged_v2_artifact_is_not_runtime_admissible(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="make-legacy-reopen-")
        self.addCleanup(temporary.cleanup)
        bundle = MakeBundleFactory(Path(temporary.name)).build("project")
        discovery = discover_project(
            bundle["root"], make_report=bundle["selection"], max_units=16,
        )
        self.assertEqual("ready", discovery["status"], discovery)
        output = bundle["harness"] / "target/run"
        artifacts = {
            "discovery": write_json_artifact(
                output, "plan/discovery.json", discovery,
            ),
        }
        stage = materialize_selected_build_ir_stage(
            bundle["root"], output, discovery, artifacts, bundle["selection"],
        )
        self.assertEqual("verified", stage["verification"]["status"], stage)
        self.assertEqual(
            BUILD_IR_SCHEMA_VERSION, stage["build_ir"]["schema_version"],
        )
        promoted = copy.deepcopy(stage["build_ir"])
        promoted["status"] = "ready"
        promoted["claim_boundary"]["closure_complete"] = True
        promoted["claim_boundary"]["generated_outputs_materialized"] = True
        promoted["boundaries"] = []
        with self.assertRaisesRegex(BuildIRValidationError, "make_claim"):
            validate_build_ir(finalize_build_ir(promoted))

        fabricated = copy.deepcopy(stage["build_ir"])
        fabricated["translation_units"][0]["output"].update({
            "materialized": True, "sha256": "f" * 64, "size_bytes": 1,
        })
        with self.assertRaisesRegex(
            BuildIRValidationError, "make_output_materialization",
        ):
            validate_build_ir(finalize_build_ir(fabricated))

        legacy = copy.deepcopy(stage["build_ir"])
        legacy["schema_version"] = LEGACY_BUILD_IR_SCHEMA_VERSION
        legacy["extractor"] = dict(LEGACY_BUILD_IR_EXTRACTOR)
        legacy["claim_boundary"].pop("link_occurrence_authority")
        for target in legacy["targets"]:
            target.pop("ordered_link_occurrences", None)
            target.pop("ordered_link_search_roots", None)
        legacy = finalize_build_ir(legacy)
        self.assertEqual(LEGACY_BUILD_IR_SCHEMA_VERSION, legacy["schema_version"])
        with self.assertRaisesRegex(BuildIRValidationError, "schema_extractor"):
            validate_build_ir(legacy)
        reference = write_json_artifact(
            output, "plan/legacy-build-ir.json", legacy,
        )
        verification = verify_build_ir_artifact(
            bundle["root"], output, reference,
        )
        self.assertEqual("blocked", verification["status"], verification)
        self.assertIn("build_ir_schema_extractor_invalid", {
            item["kind"] for item in verification["blockers"]
        })


if __name__ == "__main__":
    unittest.main()
