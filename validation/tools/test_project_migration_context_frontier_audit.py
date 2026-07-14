from __future__ import annotations

from pathlib import Path
import re
import unittest


FORBIDDEN = {
    "direct frontier projection": re.compile(
        r"\bupdate\s+context_frontiers\s+set\b", re.IGNORECASE,
    ),
    "direct frontier event append": re.compile(
        r"\binsert\s+into\s+context_frontier_events\s*\(", re.IGNORECASE,
    ),
    "frontier history mutation": re.compile(
        r"\b(?:update\s+context_frontier_events\s+set|"
        r"delete\s+from\s+context_frontier_events)\b", re.IGNORECASE,
    ),
}
EXEMPT = {
    "ledger_context_frontier_authority.py",
    "ledger_context_frontier_schema.py",
}


class ProjectMigrationContextFrontierAuditTests(unittest.TestCase):
    def test_only_frontier_authority_writes_projection_and_events(self) -> None:
        harness = Path(__file__).parent / "_project_migration_harness"
        offenders = {}
        for path in sorted(harness.glob("*.py")):
            if path.name in EXEMPT:
                continue
            source = path.read_text(encoding="utf-8")
            matches = [
                label for label, pattern in FORBIDDEN.items()
                if pattern.search(source)
            ]
            if matches:
                offenders[path.name] = matches
        self.assertEqual({}, offenders)

    def test_frontier_authority_contains_every_guarded_write(self) -> None:
        authority = (
            Path(__file__).parent / "_project_migration_harness"
            / "ledger_context_frontier_authority.py"
        ).read_text(encoding="utf-8")
        for label in (
            "direct frontier projection", "direct frontier event append",
        ):
            with self.subTest(label=label):
                self.assertIsNotNone(FORBIDDEN[label].search(authority))

    def test_scheduler_lease_and_prelaunch_require_authoritative_frontier(self) -> None:
        harness = Path(__file__).parent / "_project_migration_harness"
        scheduler = (harness / "scheduler.py").read_text(encoding="utf-8")
        lease = (harness / "ledger_lease.py").read_text(encoding="utf-8")
        runtime = (harness / "runtime_attempt_launch.py").read_text(encoding="utf-8")
        controller = (harness / "controller_runtime.py").read_text(encoding="utf-8")
        self.assertIn("validate_context_frontier_schedule_binding", scheduler)
        self.assertIn("require_ready_context_frontier", lease)
        self.assertIn("require_attempt_context_frontier", runtime)
        self.assertLess(
            controller.index("authorize_command_launch"),
            controller.index("subprocess_runner_with_environment", 500),
        )

    def test_frontier_event_versions_are_unique_per_unit(self) -> None:
        schema = (
            Path(__file__).parent / "_project_migration_harness"
            / "ledger_context_frontier_schema.py"
        ).read_text(encoding="utf-8")
        self.assertIn("unique(run_id,unit_id,to_version)", schema)


if __name__ == "__main__":
    unittest.main()
