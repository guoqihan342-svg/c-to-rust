from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_link_requirement_projection import native_link_requirement_id
from validation.tools._project_migration_harness.rust_project_ir_v3_link_expectation import ARTIFACT_KIND, SCHEMA_VERSION, layered_link_occurrence_id
from validation.tools._project_migration_harness.rust_project_ir_v3_link_validation import validate_target_occurrences


class RustProjectIRV3LinkNativeIdentityTests(unittest.TestCase):
    def test_native_name_and_format_must_recompute_requirement_identity(self) -> None:
        build_sha = "a" * 64
        target_id = "target-consumer"
        source_target_id = "build-consumer"
        requirement_id = native_link_requirement_id(
            "libportable.so", "shared-library",
        )
        occurrence = {
            "ordinal": 0,
            "occurrence_id": layered_link_occurrence_id(
                build_sha, source_target_id, 0,
            ),
            "argument_index": 0, "argument_count": 1,
            "source_kind": "external-native-library",
            "representation_layer": "native-link-input",
            "consumer_target_id": target_id,
            "input_occurrence_id": None, "binding_sha256": None,
            "object_target_id": None, "source_unit_id": None,
            "module_id": None, "package_id": None, "target_id": None,
            "external_dependency_id": "external-native-0",
            "native_requirement_id": requirement_id,
            "portable_name": "libforged.so",
            "library_format": "shared-library", "system_argument": None,
        }
        core = {
            "schema_version": SCHEMA_VERSION, "artifact_kind": ARTIFACT_KIND,
            "source_build_ir_sha256": build_sha,
            "source_target_id": source_target_id,
            "consumer_target_id": target_id, "occurrences": [occurrence],
        }
        target = {
            "target_id": target_id, "build_ir_target_id": source_target_id,
            "input_occurrences": [], "ordered_link_arguments": [],
            "link_expectation": {
                **core, "expectation_sha256": content_sha256(core),
            },
            "evidence": {"build_ir_sha256s": [build_sha]},
        }

        with self.assertRaisesRegex(ValueError, "native link mapping"):
            validate_target_occurrences(target, {requirement_id})


if __name__ == "__main__":
    unittest.main()
