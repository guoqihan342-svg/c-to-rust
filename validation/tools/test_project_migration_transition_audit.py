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
    "transition history mutation": re.compile(
        r"\b(?:update\s+transitions\s+set|delete\s+from\s+transitions)\b",
        re.IGNORECASE,
    ),
}
ALLOWED_PRIMITIVES = {
    "ledger_transition_authority.py": {
        "direct unit projection", "direct transition append",
    },
    "ledger_run_transition_authority.py": {
        "direct run projection", "direct transition append",
    },
    "ledger_schema_upgrade.py": {"direct run projection"},
}
COMMAND_CONSTRUCTOR_EXEMPT = {
    "ledger_transition_commands.py", "ledger_transition_replay.py",
}
AUTHORITY_PRIMITIVES = {
    "ledger_transition_authority.py": {
        "direct unit projection", "direct transition append",
    },
    "ledger_run_transition_authority.py": {
        "direct run projection", "direct transition append",
    },
}


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
                assignments=[{
                    "unit_id": "unit", "worker_id": "worker", "role": "translator",
                    "out_root": "target/workers/worker/out", "max_attempts": 1,
                }],
                max_concurrency=1, max_attempts=1,
            )
            with ledger.connect() as connection:
                connection.execute(
                    """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,
                       worker_id,status,fencing_token,input_sha256,started_at,metadata_json)
                       values ('attempt','run','unit','translator',1,'worker','completed',
                               1,?,?,?)""",
                    (_digest("input"), "2026-07-13T00:00:00Z", "{}"),
                )
            first = TransitionCommand(
                command_kind="host_verification_failed",
                command_id="expected-resumable:one", run_id="run", unit_id="unit",
                expected=UnitState("candidate-ready", "awaiting_gate"),
                expected_version=0, target=UnitState("retry-ready", "retryable"),
                reason="host_verification_failed", evidence_sha256=_digest("evidence"),
                attempt_id="attempt", clear_last_good_if="candidate",
            )
            drift = TransitionCommand(
                command_kind=first.command_kind, command_id=first.command_id,
                run_id="run", unit_id="unit",
                expected=UnitState("candidate-ready", "retryable"),
                expected_version=first.expected_version, target=first.target,
                reason=first.reason, evidence_sha256=first.evidence_sha256,
                attempt_id=first.attempt_id,
                clear_last_good_if=first.clear_last_good_if,
            )
            with ledger.connect() as connection:
                TransitionAuthority(connection).apply(first)
                with self.assertRaisesRegex(LedgerError, "changed its evidence binding"):
                    TransitionAuthority(connection).apply(drift)

    def test_only_transition_authority_projects_semantic_state(self) -> None:
        harness = Path(__file__).parent / "_project_migration_harness"
        offenders: dict[str, list[str]] = {}
        for path in sorted(harness.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            allowed = ALLOWED_PRIMITIVES.get(path.name, set())
            matches = [
                label for label, pattern in FORBIDDEN.items()
                if label not in allowed and pattern.search(source)
            ]
            if matches:
                offenders[path.name] = matches
        self.assertEqual({}, offenders)

    def test_authority_contains_every_guarded_projection_primitive(self) -> None:
        harness = Path(__file__).parent / "_project_migration_harness"
        for module, labels in AUTHORITY_PRIMITIVES.items():
            authority = (harness / module).read_text(encoding="utf-8")
            for label in sorted(labels):
                with self.subTest(module=module, label=label):
                    self.assertIsNotNone(FORBIDDEN[label].search(authority))

    def test_production_modules_use_registered_transition_factories(self) -> None:
        harness = Path(__file__).parent / "_project_migration_harness"
        constructor = re.compile(r"\b(?:Run)?TransitionCommand\s*\(")
        offenders = [
            path.name for path in sorted(harness.glob("*.py"))
            if path.name not in COMMAND_CONSTRUCTOR_EXEMPT
            and constructor.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
