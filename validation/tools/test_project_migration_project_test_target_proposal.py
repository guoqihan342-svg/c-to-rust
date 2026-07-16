from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import canonical_json_bytes
from validation.tools._project_migration_harness.project_migration_cli import parse_args
from validation.tools._project_migration_harness.project_plan_cli import run_plan_cli_command
from validation.tools._project_migration_harness.project_test_inventory_make_static import (
    collect_static_make_test_recipes,
)
from validation.tools._project_migration_harness.project_test_inventory_make_target import (
    select_static_make_target, verify_static_make_target_binding,
)
from validation.tools._project_migration_harness.project_test_target_proposal import (
    ProjectTestTargetProposalSelection,
    load_project_test_target_proposal,
    validate_project_test_target_proposal,
)

class ProjectTestTargetProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="make-target-proposal-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "out"
        self.build.mkdir()
        self.makefile = self.build / "Makefile"
        (self.build / "suite-bin").write_bytes(b"native-suite")
        self.makefile.write_text(
            "verify-core: suite-bin\n\t./suite-bin --strict\n",
            encoding="ascii",
        )

    def test_ai_proposal_selects_declared_literal_target(self) -> None:
        bound = self.bound_proposal("verify-core")

        selected = select_static_make_target(self.root, self.build, bound)

        self.assertEqual("selected", selected["status"])
        binding = selected["target_binding"]
        self.assertEqual("ai-static-make-target-v1", binding["kind"])
        self.assertEqual("out/Makefile", binding["entry_makefile"])
        self.assertEqual(1, binding["candidate"]["declaration"]["line"])
        self.assertEqual(
            ["./suite-bin --strict"],
            [item["command"] for item in binding["candidate"]["recipes"]],
        )
        self.assertTrue(verify_static_make_target_binding(
            self.root, self.build, binding,
        ))

    def test_undeclared_target_and_makefile_drift_fail_closed(self) -> None:
        missing = select_static_make_target(
            self.root, self.build, self.bound_proposal("verify-other"),
        )
        self.assertEqual("blocked", missing["status"])
        self.assertEqual(
            "project_test_make_proposed_target_ambiguous",
            missing["blocker"]["code"],
        )

        selected = select_static_make_target(
            self.root, self.build, self.bound_proposal("verify-core"),
        )
        self.makefile.write_text(
            "verify-core: suite-bin\n\t./suite-bin --changed\n",
            encoding="ascii",
        )
        self.assertFalse(verify_static_make_target_binding(
            self.root, self.build, selected["target_binding"],
        ))

    def test_recursive_and_parse_time_execution_constructs_are_rejected(self) -> None:
        cases = (
            "include child.mk\nverify-core:\n\t./suite-bin\n",
            "verify-core:\n\t$(MAKE) nested\n",
            "verify-core:\n\t+./suite-bin\n",
            "VALUE := $(shell ./probe)\nverify-core:\n\t./suite-bin\n",
            "$(eval verify-core: ; ./suite-bin)\n",
            "$(info ./suite-bin --strict)\nverify-core:\n\t./suite-bin\n",
            "load plugin.so\nverify-core:\n\t./suite-bin\n",
            "MAKEFLAGS =\nverify-core:\n\t./suite-bin\n",
            ".RECIPEPREFIX = >\nverify-core:\n>./suite-bin\n",
            ".ONESHELL:\nverify-core:\n\t./suite-bin\n",
            "verify-core: ; ./suite-bin\n",
        )
        proposal = self.bound_proposal("verify-core")
        for content in cases:
            with self.subTest(content=content.splitlines()[0]):
                self.makefile.write_text(content, encoding="ascii")
                selected = select_static_make_target(
                    self.root, self.build, proposal,
                )
                self.assertEqual("blocked", selected["status"])
                self.assertTrue(
                    selected["blocker"]["code"].startswith("project_test_make_"),
                )

    def test_variable_exports_and_unsupported_target_rules_fail_closed(self) -> None:
        cases = (
            "export REQUIRED_MODE=strict\n"
            "verify-core: suite-bin\n\t./suite-bin\n",
            "verify-core: export REQUIRED_MODE=strict\n\t./suite-bin\n",
            "VALUE = strict\nverify-core: suite-bin\n\t./suite-bin\n",
            "verify-core: suite-bin\n\t./suite-bin\n"
            "verify-core:: suite-bin\n\t./suite-bin\n",
            "verify-core: suite-bin\n\t./suite-bin\n"
            "verify-core: suite-bin ; ./suite-bin\n",
            "verify-core: suite-bin\n\t./suite-bin\n"
            "verify-core&: alt\n\t./alt\n",
            "verify-core: suite-bin\n\t./suite-bin\n"
            "suite-bin&: alt\n\t./alt\n",
        )
        proposal = self.bound_proposal("verify-core")
        for content in cases:
            with self.subTest(content=content.splitlines()[0]):
                self.makefile.write_text(content, encoding="ascii")
                selected = select_static_make_target(
                    self.root, self.build, proposal,
                )
                self.assertEqual("blocked", selected["status"])
                self.assertTrue(
                    selected["blocker"]["code"].startswith("project_test_make_"),
                )
    def test_literal_include_is_bound_and_include_drift_is_rejected(self) -> None:
        included = self.build / "tests.mk"
        included.write_text(
            "verify-core: suite-bin\n\t./suite-bin --strict\n",
            encoding="ascii",
        )
        self.makefile.write_text("include tests.mk\n", encoding="ascii")
        proposal = self.bound_proposal("verify-core")

        selected = select_static_make_target(self.root, self.build, proposal)

        self.assertEqual("selected", selected["status"])
        self.assertEqual(
            ["out/Makefile", "out/tests.mk"],
            [item["path"] for item in selected["target_binding"]["manifests"]],
        )
        included.write_text(
            "verify-core: suite-bin\n\t./suite-bin --changed\n",
            encoding="ascii",
        )
        self.assertFalse(verify_static_make_target_binding(
            self.root, self.build, selected["target_binding"],
        ))

    def test_dynamic_missing_and_cyclic_includes_fail_closed(self) -> None:
        child = self.build / "child.mk"
        cases = (
            "include $(TEST_RULES)\n",
            "include missing.mk\n",
            "include /tmp/external.mk\n",
        )
        proposal = self.bound_proposal("verify-core")
        for content in cases:
            with self.subTest(content=content.strip()):
                self.makefile.write_text(content, encoding="ascii")
                self.assertEqual(
                    "blocked",
                    select_static_make_target(
                        self.root, self.build, proposal,
                    )["status"],
                )
        self.makefile.write_text("include child.mk\n", encoding="ascii")
        child.write_text("include Makefile\n", encoding="ascii")
        cyclic = select_static_make_target(self.root, self.build, proposal)
        self.assertEqual("project_test_make_include_cycle", cyclic["blocker"]["code"])

    def test_comment_phony_and_prerequisite_mentions_are_not_declarations(self) -> None:
        proposal = self.bound_proposal("verify-core")
        self.makefile.write_text(
            "# verify-core: ignored\n.PHONY: verify-core\n"
            "all: verify-core\n\t./suite-bin --strict\n",
            encoding="ascii",
        )

        selected = select_static_make_target(self.root, self.build, proposal)

        self.assertEqual("blocked", selected["status"])
        self.assertEqual(
            "project_test_make_proposed_target_ambiguous",
            selected["blocker"]["code"],
        )

    def test_target_injection_and_unbound_provenance_are_rejected(self) -> None:
        for target in (
            "--eval=bad", "../verify", "verify;run", "$(shell-run)",
            "verify%", "verify=value",
        ):
            with self.subTest(target=target):
                with self.assertRaisesRegex(
                    ValueError, "project_test_target_proposal_schema_invalid",
                ):
                    validate_project_test_target_proposal(self.payload(target))

        invalid = self.payload("verify-core")
        invalid["producer"]["kind"] = "host-assertion"
        with self.assertRaisesRegex(
            ValueError, "project_test_target_proposal_schema_invalid",
        ):
            validate_project_test_target_proposal(invalid)

    def test_bound_input_must_be_canonical_and_unchanged(self) -> None:
        selection = self.selection("verify-core")
        selection.path.write_bytes(b'{"target":"verify-core"}\n')

        with self.assertRaisesRegex(
            ValueError, "project_test_target_proposal_input_drifted",
        ):
            load_project_test_target_proposal(selection)

        noncanonical = self.root / "noncanonical.json"
        noncanonical.write_text(
            '{"schema_version":1,"artifact_kind":"project-test-target-proposal-v1"}',
            encoding="ascii",
        )
        data = noncanonical.read_bytes()
        with self.assertRaisesRegex(
            ValueError, "project_test_target_proposal_json_not_canonical",
        ):
            load_project_test_target_proposal(ProjectTestTargetProposalSelection(
                noncanonical, hashlib.sha256(data).hexdigest(), len(data),
            ))

    def test_cli_passes_bound_proposal_to_real_plan_entry(self) -> None:
        selection = self.selection("verify-core")
        args = parse_args([
            "migrate", "--repo-root", str(self.root),
            "--project-test-target-proposal", str(selection.path),
            "--project-test-target-proposal-sha256", selection.sha256,
            "--project-test-target-proposal-size-bytes", str(selection.size_bytes),
        ])
        with patch(
            "validation.tools._project_migration_harness.project_plan_cli.plan_project",
            return_value={"status": "planned"},
        ) as planner:
            run_plan_cli_command(args, harness_root=self.root)

        planned = planner.call_args.kwargs["project_test_target_proposal"]
        self.assertTrue(planned.path.samefile(selection.path))
        self.assertEqual(selection.sha256, planned.sha256)
        self.assertEqual(selection.size_bytes, planned.size_bytes)

    def test_cli_rejects_partial_proposal_binding(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args([
                "migrate", "--repo-root", str(self.root),
                "--project-test-target-proposal", "proposal.json",
            ])

    def test_collector_never_launches_make_or_any_subprocess(self) -> None:
        bound = self.bound_proposal("verify-core")
        with patch("subprocess.run") as runner:
            collected = collect_static_make_test_recipes(
                self.root, self.build, target_proposal=bound,
            )

        self.assertEqual("collected", collected["status"])
        self.assertEqual(
            ["./suite-bin --strict"], collected["observation"]["commands"],
        )
        self.assertFalse(collected["observation"]["subprocess_executed"])
        runner.assert_not_called()

    def selection(self, target: str) -> ProjectTestTargetProposalSelection:
        path = self.root / f"proposal-{target.replace('/', '_')}.json"
        data = canonical_json_bytes(self.payload(target))
        path.write_bytes(data)
        return ProjectTestTargetProposalSelection(
            path, hashlib.sha256(data).hexdigest(), len(data),
        )

    def bound_proposal(self, target: str) -> dict:
        return load_project_test_target_proposal(self.selection(target))

    @staticmethod
    def payload(target: str) -> dict:
        return {
            "schema_version": 1,
            "artifact_kind": "project-test-target-proposal-v1",
            "build_system": "make",
            "target": target,
            "producer": {
                "kind": "ai-candidate", "provider": "zai",
                "model": "glm-5.1", "prompt_sha256": "a" * 64,
                "response_sha256": "b" * 64,
            },
            "claim_boundary": {
                "semantic_gate": False, "translation_coverage_numerator": 0,
            },
        }

if __name__ == "__main__":
    unittest.main()
