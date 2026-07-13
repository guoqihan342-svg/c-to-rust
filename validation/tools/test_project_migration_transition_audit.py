from __future__ import annotations

import hashlib
from pathlib import Path
import re
import tempfile
import unittest

from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.ledger_transition_authority import (
    TransitionAuthority,
)
from validation.tools._project_migration_harness.ledger_transition_policy import (
    TransitionCommand, UnitState,
)


FORBIDDEN = {
    "direct unit projection": re.compile(
        r"\bupdate\s+migration_units\s+set\b", re.IGNORECASE,
    ),
    "direct run projection": re.compile(
        r"\bupdate\s+project_runs\s+set\b", re.IGNORECASE,
    ),
    "direct transition append": re.compile(
        r"\binsert\s+into\s+transitions\s*\(", re.IGNORECASE,
    ),
}
EXEMPT = {"ledger_schema.py", "ledger_transition_authority.py"}


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ProjectMigrationTransitionAuditTests(unittest.TestCase):
    def test_replay_rejects_expected_resumable_status_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="transition-expected-binding-") as root:
            ledger = ProjectLedger(Path(root) / "ledger.sqlite3")
            ledger.create_run(
                run_id="run", project_key="project", source_commit="commit",
                dag_sha256=_digest("dag"),
                units=[{
                    "unit_id": "unit", "group_id": "unit", "wave_index": 0,
                    "status": "candidate-ready", "resumable_status": "awaiting_gate",
                    "content_sha256": _digest("unit"),
                }],
                assignments=[], max_concurrency=1, max_attempts=1,
            )
            first = TransitionCommand(
                command_id="expected-resumable:one", run_id="run", unit_id="unit",
                expected=UnitState("candidate-ready", "awaiting_gate"),
                target=UnitState("retry-ready", "retryable"),
                reason="test_transition", evidence_sha256=_digest("evidence"),
            )
            drift = TransitionCommand(
                command_id=first.command_id, run_id="run", unit_id="unit",
                expected=UnitState("candidate-ready", "retryable"),
                target=first.target, reason=first.reason,
                evidence_sha256=first.evidence_sha256,
            )
            with ledger.connect() as connection:
                TransitionAuthority(connection).apply(first)
                with self.assertRaisesRegex(LedgerError, "changed its evidence binding"):
                    TransitionAuthority(connection).apply(drift)

    def test_only_transition_authority_projects_semantic_state(self) -> None:
        harness = Path(__file__).parent / "_project_migration_harness"
        offenders: dict[str, list[str]] = {}
        for path in sorted(harness.glob("*.py")):
            if path.name in EXEMPT:
                continue
            source = path.read_text(encoding="utf-8")
            matches = [label for label, pattern in FORBIDDEN.items() if pattern.search(source)]
            if matches:
                offenders[path.name] = matches
        self.assertEqual({}, offenders)

    def test_authority_contains_every_guarded_projection_primitive(self) -> None:
        authority = (
            Path(__file__).parent / "_project_migration_harness"
            / "ledger_transition_authority.py"
        ).read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN.items():
            with self.subTest(label=label):
                self.assertIsNotNone(pattern.search(authority))


if __name__ == "__main__":
    unittest.main()
