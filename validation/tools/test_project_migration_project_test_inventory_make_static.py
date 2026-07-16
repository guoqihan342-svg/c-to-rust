from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes, content_sha256,
)
from validation.tools._project_migration_harness.project_test_inventory_make_static import (
    MAKE_STATIC_ADAPTER, collect_static_make_test_recipes,
    inventory_from_static_make_observation,
)
from validation.tools._project_migration_harness.project_test_inventory import (
    collect_project_test_inventory,
)
from validation.tools._project_migration_harness.project_test_target_proposal import (
    ProjectTestTargetProposalSelection, load_project_test_target_proposal,
)
from validation.tools._project_migration_harness.model_safe_test_contract import (
    build_model_safe_test_contract,
)


class StaticMakeProjectTestInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="static-make-inventory-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.binary = self.build / "suite-bin"
        self.binary.write_bytes(b"native-test-binary")
        (self.root / "fixture.txt").write_text("fixture", encoding="ascii")
        (self.build / "Makefile").write_text(
            "verify-core: suite-bin\n"
            "\t@echo preparing\n"
            "\tMODE=portable ./suite-bin ../fixture.txt --strict\n",
            encoding="ascii",
        )
        self.selection = self._selection()
        self.proposal = load_project_test_target_proposal(self.selection)
        self.source_ref = {
            "path": "plan/static-make.json", "sha256": "d" * 64,
            "size_bytes": 10,
        }

    def test_static_recipe_derives_ready_inventory(self) -> None:
        collected = collect_static_make_test_recipes(
            self.root, self.build, target_proposal=self.proposal,
        )
        inventory = inventory_from_static_make_observation(
            self.root, self._build_ir(), collected["observation"],
            source_observation=self.source_ref,
        )

        self.assertEqual("ready", inventory["status"], inventory)
        self.assertEqual(MAKE_STATIC_ADAPTER, inventory["adapter"])
        self.assertEqual(1, len(inventory["tests"]))
        test = inventory["tests"][0]
        self.assertEqual("link-target", test["source_target_id"])
        self.assertEqual({
            "MODE": {"kind": "literal", "value": "portable"},
        }, test["environment"])
        self.assertEqual([
            {"kind": "repo-path", "path": "fixture.txt"},
            {"kind": "literal", "value": "--strict"},
        ], test["arguments"])
        self.assertEqual(
            inventory["inventory_sha256"],
            content_sha256({
                key: value for key, value in inventory.items()
                if key != "inventory_sha256"
            }),
        )
        contract = build_model_safe_test_contract(
            inventory, group_id="group-neutral",
            target_scope={
                "scope_sha256": "e" * 64,
                "reachable_target_ids": ["link-target"],
                "terminal_target_ids": [],
            },
        )
        self.assertEqual(MAKE_STATIC_ADAPTER, contract["adapter"])

    def test_bound_ai_proposal_reaches_project_inventory_entrypoint(self) -> None:
        metadata = self.build / "make-report.json"
        metadata.write_text("{}\n", encoding="ascii")
        build_ir = self._build_ir()
        build_ir["build_metadata"] = [{"path": "build/make-report.json"}]

        inventory = collect_project_test_inventory(
            self.root,
            {"build_system_facts": {"systems": ["make"]}},
            build_ir,
            output=self.root / "artifacts",
            target_proposal=self.selection,
        )

        self.assertEqual("ready", inventory["status"], inventory)
        self.assertEqual(MAKE_STATIC_ADAPTER, inventory["adapter"])
        self.assertTrue(
            (self.root / "artifacts/plan/project-test-make-static-observation.json").is_file(),
        )

    def test_observation_injection_and_recipe_drift_fail_closed(self) -> None:
        collected = collect_static_make_test_recipes(
            self.root, self.build, target_proposal=self.proposal,
        )
        observation = collected["observation"]
        injected = {**observation, "commands": [
            *observation["commands"], "./suite-bin --injected",
        ]}
        injected["commands_sha256"] = content_sha256(injected["commands"])
        injected["observation_sha256"] = content_sha256({
            key: value for key, value in injected.items()
            if key != "observation_sha256"
        })

        inventory = inventory_from_static_make_observation(
            self.root, self._build_ir(), injected,
            source_observation=self.source_ref,
        )
        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_make_static_schema_invalid",
            inventory["blockers"][0]["code"],
        )

        binding = observation["target_binding"]
        (self.build / "Makefile").write_text(
            "verify-core: suite-bin\n\t./suite-bin --changed\n",
            encoding="ascii",
        )
        recollected = collect_static_make_test_recipes(
            self.root, self.build, expected_target_binding=binding,
        )
        self.assertEqual("blocked", recollected["status"])
        self.assertEqual(
            "project_test_make_static_binding_drifted",
            recollected["blocker"]["code"],
        )

    def test_dynamic_recipe_never_reaches_inventory(self) -> None:
        for recipe in (
            "\t$(info ./suite-bin --forged)\n",
            "\t./suite-bin && ./suite-bin\n",
            "\t-python3 run-tests.py\n",
        ):
            with self.subTest(recipe=recipe.strip()):
                (self.build / "Makefile").write_text(
                    "verify-core: suite-bin\n" + recipe,
                    encoding="ascii",
                )
                collected = collect_static_make_test_recipes(
                    self.root, self.build, target_proposal=self.proposal,
                )
                if collected["status"] == "collected":
                    inventory = inventory_from_static_make_observation(
                        self.root, self._build_ir(), collected["observation"],
                        source_observation=self.source_ref,
                    )
                    self.assertEqual("blocked", inventory["status"])
                else:
                    self.assertEqual("blocked", collected["status"])

    def test_unmaterialized_setup_prerequisite_cannot_be_skipped(self) -> None:
        (self.build / "Makefile").write_text(
            "verify-core: setup suite-bin\n\t./suite-bin --strict\n"
            "setup:\n\t./prepare-fixtures\n",
            encoding="ascii",
        )
        collected = collect_static_make_test_recipes(
            self.root, self.build, target_proposal=self.proposal,
        )

        self.assertEqual("blocked", collected["status"])
        self.assertEqual(
            "project_test_make_prerequisite_not_direct_leaf",
            collected["blocker"]["code"],
        )

    def test_materialized_phony_prerequisite_cannot_be_skipped(self) -> None:
        helper = self.build / "setup-helper"
        helper.write_bytes(b"materialized-helper")
        (self.build / "Makefile").write_text(
            ".PHONY: setup-helper\n"
            "verify-core: setup-helper suite-bin\n\t./suite-bin --strict\n"
            "setup-helper:\n\t./prepare-fixtures\n",
            encoding="ascii",
        )
        build_ir = self._build_ir()
        data = helper.read_bytes()
        build_ir["targets"].append({
            "target_id": "helper-target", "kind": "link",
            "outputs": [{
                "path": "build/setup-helper", "kind": "file",
                "materialized": True,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }],
        })

        collected = collect_static_make_test_recipes(
            self.root, self.build, target_proposal=self.proposal,
        )

        self.assertEqual("blocked", collected["status"])
        self.assertEqual(
            "project_test_make_prerequisite_phony",
            collected["blocker"]["code"],
        )

    def test_prerequisite_content_drift_cannot_reopen_inventory(self) -> None:
        collected = collect_static_make_test_recipes(
            self.root, self.build, target_proposal=self.proposal,
        )
        self.binary.write_bytes(b"changed-after-selection")

        inventory = inventory_from_static_make_observation(
            self.root, self._build_ir(), collected["observation"],
            source_observation=self.source_ref,
        )

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_make_static_binding_invalid",
            inventory["blockers"][0]["code"],
        )

    def _build_ir(self) -> dict:
        data = self.binary.read_bytes()
        return {"targets": [{
            "target_id": "link-target", "kind": "link",
            "outputs": [{
                "path": "build/suite-bin", "kind": "file",
                "materialized": True,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }],
        }]}

    def _selection(self) -> ProjectTestTargetProposalSelection:
        value = {
            "schema_version": 1,
            "artifact_kind": "project-test-target-proposal-v1",
            "build_system": "make", "target": "verify-core",
            "producer": {
                "kind": "ai-candidate", "provider": "neutral-provider",
                "model": "neutral-model", "prompt_sha256": "a" * 64,
                "response_sha256": "b" * 64,
            },
            "claim_boundary": {
                "semantic_gate": False, "translation_coverage_numerator": 0,
            },
        }
        data = canonical_json_bytes(value)
        path = self.root / "proposal.json"
        path.write_bytes(data)
        return ProjectTestTargetProposalSelection(
            path, hashlib.sha256(data).hexdigest(), len(data),
        )


if __name__ == "__main__":
    unittest.main()
