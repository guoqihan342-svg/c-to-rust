from __future__ import annotations

import argparse
from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_cli_runtime import exit_code
from validation.tools._project_migration_harness.project_migrate_cli import (
    run_migrate_cli_command,
)
from validation.tools._project_migration_harness.project_migration_cli import (
    parse_args,
)


class ProjectMigrationMigrateCliTests(unittest.TestCase):
    def test_parser_combines_competition_plan_and_completion_defaults(self) -> None:
        parsed = parse_args(["migrate", "--repo-root", "source"])

        self.assertEqual("competition", parsed.profile)
        self.assertEqual("required", parsed.build_closure_policy)
        self.assertEqual("GLM-5.1", parsed.logical_model)
        self.assertEqual("zai/glm-5.1", parsed.resolved_model)
        self.assertEqual(4, parsed.max_concurrency)
        self.assertEqual(5, parsed.max_attempts)
        self.assertEqual(256, parsed.max_cycles)
        for field in ("plan", "opencode_command", "agent", "variant", "status"):
            self.assertFalse(hasattr(parsed, field))

    def test_blocked_plan_never_enters_completion(self) -> None:
        args = argparse.Namespace(out_root="target/run")
        blocked = {"schema_version": 1, "status": "blocked"}

        with (
            mock.patch(
                "validation.tools._project_migration_harness.project_migrate_cli."
                "run_plan_cli_command",
                return_value=blocked,
            ),
            mock.patch(
                "validation.tools._project_migration_harness.project_migrate_cli."
                "run_completion_cli_command",
            ) as completion,
        ):
            result = run_migrate_cli_command(args, harness_root=Path("."))

        self.assertIs(blocked, result)
        completion.assert_not_called()

    def test_planned_run_uses_generated_plan_and_completion_state_machine(self) -> None:
        args = argparse.Namespace(out_root="target/run", repo_root=Path("source"))
        completed = {"schema_version": 1, "status": "completed"}

        with (
            mock.patch(
                "validation.tools._project_migration_harness.project_migrate_cli."
                "run_plan_cli_command",
                return_value={"schema_version": 1, "status": "planned"},
            ),
            mock.patch(
                "validation.tools._project_migration_harness.project_migrate_cli."
                "project_cli_runtime.target_relative",
                return_value="target/run",
            ),
            mock.patch(
                "validation.tools._project_migration_harness.project_migrate_cli."
                "run_completion_cli_command",
                return_value=completed,
            ) as completion,
        ):
            result = run_migrate_cli_command(args, harness_root=Path("."))

        self.assertIs(completed, result)
        command, completion_args = completion.call_args.args
        self.assertEqual("run-to-completion", command)
        self.assertEqual(
            Path("target/run/project-migration-plan.json"), completion_args.plan,
        )
        self.assertEqual(Path("source"), completion_args.repo_root)

    def test_migrate_exit_code_requires_completed(self) -> None:
        self.assertEqual(1, exit_code({"status": "waiting"}, command="migrate"))
        self.assertEqual(1, exit_code({"status": "passed"}, command="migrate"))
        self.assertEqual(0, exit_code({"status": "completed"}, command="migrate"))

    def test_root_opencode_rule_points_to_the_canonical_entrypoint(self) -> None:
        root = Path(__file__).resolve().parents[2]
        rules = (root / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("project_migration_harness.py migrate", rules)
        self.assertIn("status=completed", rules)
        self.assertIn("Task mode: generate-candidate", rules)
        self.assertIn("不允许在 `plan`", rules)


if __name__ == "__main__":
    unittest.main()
