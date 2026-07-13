from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from validation.tools._project_migration_harness.held_out_acceptance import (
    HeldOutContractError,
    file_sha256,
    repository_tree_sha256,
    run_acceptance_suite,
    validate_manifest,
)


SOURCES = [
    """int fold(int n) {
  int x = n;
  x += 1; x += 2; x += 3; x += 4; x += 5; x += 6;
  x += 7; x += 8; x += 9; x += 10; x += 11; x += 12;
  return x;
}
""",
    """struct pair { int left; int right; };
int pair_total(const struct pair *value) {
  return value == 0 ? 0 : value->left + value->right;
}
""",
    """enum state { STATE_IDLE, STATE_BUSY, STATE_DONE };
int state_code(enum state value) {
  switch (value) { case STATE_BUSY: return 7; case STATE_DONE: return 9; default: return 0; }
}
""",
    """int maximum(const int *items, unsigned long count) {
  unsigned long i = 1; int result = count ? items[0] : 0;
  while (i < count) { if (items[i] > result) result = items[i]; ++i; }
  return result;
}
""",
    """typedef int (*operation)(int, int);
int apply(operation callback, int first, int second) {
  if (!callback) return -1;
  return callback(first, second);
}
""",
]


class ProjectMigrationHeldOutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.planner = self.root / "planner.py"
        self.planner.write_text("print('{}')\n", encoding="utf-8")
        self.repos = [self._repo(source) for source in SOURCES]
        self.manifest = self._manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_finite_renamed_neutral_repository_contract(self) -> None:
        validated = validate_manifest(
            self.manifest, manifest_dir=self.root,
            harness_root=self.root, mode="offline-contract",
        )

        self.assertEqual(validated["project_count"], 5)
        self.assertEqual(len(validated["construct_families"]), 15)
        self.assertEqual(validated["held_out_project_count"], 2)
        self.assertEqual(validated["identity_scan"]["status"], "passed")

    def test_rejects_renamed_duplicate_project_content(self) -> None:
        source = self.repos[4] / "src" / "unit.c"
        source.write_text(SOURCES[0], encoding="utf-8")
        self._refresh_case(4)

        with self.assertRaisesRegex(HeldOutContractError, "duplicate project content"):
            self._validate()

    def test_rejects_near_duplicate_project_shape(self) -> None:
        source = self.repos[4] / "src" / "unit.c"
        source.write_text(SOURCES[0].replace("x += 7", "x -= 7"), encoding="utf-8")
        self._refresh_case(4)

        with self.assertRaisesRegex(HeldOutContractError, "near-duplicate projects"):
            self._validate()

    def test_rejects_identity_dispatch_in_generic_entrypoint(self) -> None:
        project_id = self.manifest["cases"][0]["project_id"]
        self.planner.write_text(f"selected = '{project_id}'\n", encoding="utf-8")
        self.manifest["generic_plan_entrypoint"]["sha256"] = file_sha256(self.planner)

        with self.assertRaisesRegex(HeldOutContractError, "identity dispatch"):
            self._validate()

    def test_rejects_missing_true_held_out_projects(self) -> None:
        for case in self.manifest["cases"]:
            case["participated_in_rule_development"] = True

        with self.assertRaisesRegex(HeldOutContractError, "two true held-out"):
            self._validate()

    def test_rejects_compile_database_hash_drift(self) -> None:
        self.manifest["cases"][0]["compile_database"]["sha256"] = "0" * 64

        with self.assertRaisesRegex(HeldOutContractError, "compile_database.sha256 mismatch"):
            self._validate()

    def test_rejects_case_supplied_translation_evidence(self) -> None:
        self.manifest["cases"][0]["translation_evidence"] = {
            "path": "self-reported.json", "sha256": "0" * 64,
        }

        with self.assertRaisesRegex(HeldOutContractError, "fields are forbidden"):
            self._validate()

    def test_repository_tree_resource_limit_is_fail_closed(self) -> None:
        with mock.patch(
            "validation.tools._project_migration_harness."
            "held_out_integrity.MAX_TREE_FILES",
            1,
        ):
            with self.assertRaisesRegex(HeldOutContractError, "resource limit"):
                repository_tree_sha256(self.repos[0])

    def test_offline_plans_are_content_addressed_but_not_translation_success(self) -> None:
        calls: list[list[str]] = []

        def plan(argv: list[str]) -> dict:
            calls.append(argv)
            return {
                "status": "planned", "plan_sha256": "a" * 64,
                "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
            }

        result = run_acceptance_suite(
            self.manifest, manifest_dir=self.root, harness_root=self.root,
            mode="offline-contract", out_root="target/out", plan_runner=plan,
        )

        self.assertEqual(len(calls), 5)
        self.assertEqual(result["status"], "contract_passed")
        self.assertEqual(result["accepted_projects"], 0)
        self.assertFalse(result["claim_boundary"]["semantic_gate"])
        for ref in result["case_evidence"] + [result["summary_evidence"]]:
            self.assertEqual(Path(ref["path"]).stem, ref["sha256"])
            self.assertEqual(
                file_sha256(self.root / "target" / "out" / ref["path"]),
                ref["sha256"],
            )

    def test_rejects_output_outside_target_before_plan(self) -> None:
        plan = mock.Mock()

        with self.assertRaisesRegex(HeldOutContractError, "target directory"):
            run_acceptance_suite(
                self.manifest, manifest_dir=self.root,
                harness_root=self.root, mode="offline-contract",
                out_root="out", plan_runner=plan,
            )

        plan.assert_not_called()
        self.assertFalse((self.root / "out").exists())

    def test_rejects_linklike_output_component_before_plan(self) -> None:
        linked = self.root / "target" / "linked"
        linked.mkdir(parents=True)
        plan = mock.Mock()
        original = Path.resolve(linked)

        with mock.patch(
            "validation.tools._project_migration_harness.held_out_integrity._linklike",
            side_effect=lambda path: path.resolve() == original,
        ):
            with self.assertRaisesRegex(HeldOutContractError, "linked or reparse"):
                run_acceptance_suite(
                    self.manifest, manifest_dir=self.root,
                    harness_root=self.root, mode="offline-contract",
                    out_root="target/linked", plan_runner=plan,
                )

        plan.assert_not_called()

    def test_rejects_plan_that_claims_translation_success(self) -> None:
        def invalid_plan(_: list[str]) -> dict:
            return {
                "status": "planned", "plan_sha256": "b" * 64,
                "claim_boundary": {"semantic_gate": True, "translation_coverage_numerator": 1},
            }

        with self.assertRaisesRegex(HeldOutContractError, "planning must not claim"):
            run_acceptance_suite(
                self.manifest, manifest_dir=self.root, harness_root=self.root,
                mode="offline-contract", out_root="target/out", plan_runner=invalid_plan,
            )

    def test_real_mode_cannot_accept_a_self_reported_json_file(self) -> None:
        commits = {
            repo.resolve(): self.manifest["cases"][index]["repository"]["source_commit"]
            for index, repo in enumerate(self.repos)
        }

        def fake_workflow(argv: list[str]) -> dict:
            out_root = argv[argv.index("--out-root") + 1]
            ledger = self.root / out_root / "state" / "project-migration.sqlite3"
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text(
                json.dumps({"status": "passed", "semantic_gate": True}),
                encoding="utf-8",
            )
            return {
                "schema_version": 1,
                "status": "planned",
                "plan_sha256": "c" * 64,
                "ledger": {
                    "path": f"{out_root}/state/project-migration.sqlite3",
                    "status": "bound",
                },
                "claim_boundary": {
                    "semantic_gate": False,
                    "translation_coverage_numerator": 0,
                },
            }

        with mock.patch(
            "validation.tools._project_migration_harness.held_out_acceptance._git_head",
            side_effect=lambda repo: commits[repo.resolve()],
        ):
            result = run_acceptance_suite(
                self.manifest, manifest_dir=self.root, harness_root=self.root,
                mode="real-projects", out_root="target/out", plan_runner=fake_workflow,
            )

        self.assertEqual("incomplete", result["status"])
        self.assertEqual(0, result["accepted_projects"])
        self.assertFalse(result["claim_boundary"]["semantic_gate"])

    def _validate(self) -> dict:
        return validate_manifest(
            self.manifest, manifest_dir=self.root,
            harness_root=self.root, mode="offline-contract",
        )

    def _repo(self, source: str) -> Path:
        repo = self.root / f"neutral-{uuid.uuid4().hex[:10]}"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "unit.c").write_text(source, encoding="utf-8")
        compile_db = [{
            "directory": ".", "file": "src/unit.c",
            "arguments": ["cc", "-c", "src/unit.c"],
        }]
        (repo / "compile_commands.json").write_text(
            json.dumps(compile_db, indent=2) + "\n", encoding="utf-8",
        )
        return repo

    def _manifest(self) -> dict:
        families = [f"construct-{index:02d}" for index in range(15)]
        cases = []
        for index, repo in enumerate(self.repos):
            compile_db = repo / "compile_commands.json"
            cases.append({
                "case_id": f"case-{index}", "project_id": f"neutral-{index}",
                "repository": {
                    "path": repo.name, "source_commit": f"{index + 1:040x}",
                    "tree_sha256": repository_tree_sha256(repo),
                },
                "compile_database": {"path": "compile_commands.json", "sha256": file_sha256(compile_db)},
                "participated_in_rule_development": index >= 2,
                "construct_families": families[index * 3:index * 3 + 3],
            })
        return {
            "schema_version": 1, "suite_id": "neutral-suite",
            "generic_plan_entrypoint": {"path": self.planner.name, "sha256": file_sha256(self.planner)},
            "cases": cases,
        }

    def _refresh_case(self, index: int) -> None:
        case = self.manifest["cases"][index]
        case["repository"]["tree_sha256"] = repository_tree_sha256(self.repos[index])
        case["compile_database"]["sha256"] = file_sha256(self.repos[index] / "compile_commands.json")


if __name__ == "__main__":
    unittest.main()
