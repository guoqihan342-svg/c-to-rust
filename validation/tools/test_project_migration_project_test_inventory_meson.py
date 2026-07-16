from __future__ import annotations

import copy
import hashlib
import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_test_inventory_meson_parse import (
    inventory_from_meson_observation,
)
from validation.tools._project_migration_harness.project_test_inventory_meson_binding import (
    capture_meson_test_build_binding,
)
from validation.tools._project_migration_harness.project_test_inventory_meson_schema import (
    MAX_PROJECT_TESTS,
)
from validation.tools.project_migration_project_test_inventory_meson_test_support import (
    MesonInventoryTestCase,
)


class MesonProjectTestInventoryTests(MesonInventoryTestCase):
    def test_direct_exitcode_test_maps_to_materialized_build_ir_target(self) -> None:
        inventory = self.inventory(self.tests)

        self.assertEqual("ready", inventory["status"], inventory)
        self.assertEqual("meson-introspect-tests-v1", inventory["adapter"])
        self.assertEqual(1, len(inventory["tests"]))
        test = inventory["tests"][0]
        self.assertEqual("link-target", test["source_target_id"])
        self.assertEqual([
            {"kind": "repo-path", "path": "fixture.txt"},
            {"kind": "literal", "value": "--strict"},
        ], test["arguments"])
        self.assertEqual({
            "MODE": {"kind": "literal", "value": "portable"},
        }, test["environment"])
        self.assertEqual("suite@exe", test["adapter_metadata"]["meson_target_id"])

    def test_zero_test_inventory_fails_closed(self) -> None:
        inventory = self.inventory([])

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_inventory_empty", inventory["blockers"][0]["code"],
        )

    def test_runner_or_wrapper_cannot_replace_direct_executable(self) -> None:
        runner = self.direct_test(cmd=["/usr/bin/python3", str(self.binary)])

        inventory = self.inventory([runner])

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_meson_runner_or_wrapper_unsupported",
            inventory["blockers"][0]["code"],
        )

    def test_protocol_fixture_path_and_reserved_environment_are_blockers(self) -> None:
        cases = (
            (
                self.direct_test(protocol="tap"),
                "project_test_meson_protocol_unsupported",
            ),
            (
                self.direct_test(depends=["suite@exe", "fixture@cus"]),
                "project_test_meson_fixture_or_dependency_unsupported",
            ),
            (
                self.direct_test(extra_paths=[str(self.build)]),
                "project_test_meson_environment_unsupported",
            ),
            (
                self.direct_test(env={"PATH": "/outside"}),
                "project_test_meson_environment_invalid",
            ),
        )
        for test, code in cases:
            with self.subTest(code=code):
                inventory = self.inventory([test])
                self.assertEqual("blocked", inventory["status"])
                self.assertEqual(code, inventory["blockers"][0]["code"])

    def test_unknown_stdin_field_and_malformed_hash_fail_closed(self) -> None:
        unknown = self.direct_test(stdin="fixture.txt")
        inventory = self.inventory([unknown])
        self.assertEqual(
            "project_test_meson_record_schema_invalid",
            inventory["blockers"][0]["code"],
        )

        observation = self.current_observation(self.tests)
        observation["payload_sha256"] = "0" * 64
        inventory = inventory_from_meson_observation(
            self.root, self.build_ir, observation,
            source_observation=self.source_ref,
        )
        self.assertEqual(
            "project_test_meson_schema_invalid",
            inventory["blockers"][0]["code"],
        )

    def test_oversized_test_list_fails_closed_before_record_derivation(self) -> None:
        tests = [self.direct_test()] * (MAX_PROJECT_TESTS + 1)

        inventory = self.inventory(tests)

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_meson_schema_invalid",
            inventory["blockers"][0]["code"],
        )

    def test_unmapped_and_ambiguous_meson_targets_fail_closed(self) -> None:
        other = self.write("build/other-bin", b"other")
        unmapped = self.direct_test(cmd=[str(other)])
        inventory = self.inventory([unmapped])
        self.assertEqual(
            "project_test_executable_target_unmapped",
            inventory["blockers"][0]["code"],
        )

        changed = copy.deepcopy(self.build_ir)
        other_data = other.read_bytes()
        changed["targets"].append({
            "target_id": "other-target", "kind": "link",
            "outputs": [{
                "path": "build/other-bin", "kind": "file",
                "materialized": True,
                "sha256": hashlib.sha256(other_data).hexdigest(),
                "size_bytes": len(other_data),
            }],
            "provenance": {
                "raw_fact_role": "generated-build-closure",
                "meson_target_id": "suite@exe",
            },
        })
        inventory = self.inventory(self.tests, build_ir=changed)
        self.assertEqual(
            "project_test_meson_target_mapping_ambiguous",
            inventory["blockers"][0]["code"],
        )

    def test_observation_and_inventory_hashes_bind_payload(self) -> None:
        observation = self.current_observation(self.tests)
        inventory = inventory_from_meson_observation(
            self.root, self.build_ir, observation,
            source_observation=self.source_ref,
        )

        self.assertEqual(
            observation["observation_sha256"],
            content_sha256({
                key: value for key, value in observation.items()
                if key != "observation_sha256"
            }),
        )
        self.assertEqual(
            inventory["inventory_sha256"],
            content_sha256({
                key: value for key, value in inventory.items()
                if key != "inventory_sha256"
            }),
        )

    def test_missing_intro_tests_manifest_declaration_fails_closed(self) -> None:
        info = self.info / "meson-info.json"
        payload = json.loads(info.read_text(encoding="utf-8"))
        del payload["introspection"]["information"]["tests"]
        info.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(
            ValueError, "project_test_meson_build_binding_invalid",
        ):
            capture_meson_test_build_binding(self.root, self.database)

    def current_observation(self, tests: list[dict]) -> dict:
        self.tests = tests
        self.write_tests(tests)
        return self.observation(tests)

    def inventory(self, tests: list[dict], *, build_ir: dict | None = None) -> dict:
        observation = self.current_observation(tests)
        return inventory_from_meson_observation(
            self.root, build_ir or self.build_ir, observation,
            source_observation=self.source_ref,
        )


if __name__ == "__main__":
    unittest.main()
