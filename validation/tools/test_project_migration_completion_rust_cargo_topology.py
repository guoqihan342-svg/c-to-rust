from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_completion_topology_binding import (
    validate_completion_rust_cargo_topology,
)


MODULE = (
    "validation.tools._project_migration_harness."
    "project_completion_topology_binding.reopen_project_rust_cargo_topology"
)


class CompletionRustCargoTopologyTests(unittest.TestCase):
    def test_v3_completion_reopens_ready_topology(self) -> None:
        root, receipt = _fixture()
        with mock.patch(MODULE, return_value={"status": "ready"}) as reopen:
            validate_completion_rust_cargo_topology(root, receipt)

        reopen.assert_called_once_with(
            ledger_path=(
                root.resolve(strict=True) / "state" / "project-migration.sqlite3"
            ),
            reference=receipt["rust_cargo_topology_evidence"],
            run_id="run", candidate_set_sha256="c" * 64,
        )

    def test_v3_completion_rejects_blocked_topology(self) -> None:
        root, receipt = _fixture()
        with (
            mock.patch(MODULE, return_value={"status": "blocked"}),
            self.assertRaisesRegex(LedgerError, "requires ready"),
        ):
            validate_completion_rust_cargo_topology(root, receipt)

    def test_v2_completion_does_not_claim_topology(self) -> None:
        root, receipt = _fixture()
        receipt["schema_version"] = 2
        receipt.pop("rust_cargo_topology_evidence")
        with mock.patch(MODULE) as reopen:
            validate_completion_rust_cargo_topology(root, receipt)
        reopen.assert_not_called()


def _fixture() -> tuple[Path, dict]:
    temporary = tempfile.TemporaryDirectory(prefix="completion-topology-")
    root = Path(temporary.name)
    # Keep the temporary owner alive for the duration of each test process.
    _TEMPORARIES.append(temporary)
    database = root / "state" / "project-migration.sqlite3"
    database.parent.mkdir()
    database.touch()
    return root, {
        "schema_version": 3, "run_id": "run",
        "candidate_set_sha256": "c" * 64,
        "rust_cargo_topology_evidence": {
            "path": "verification/project-rust-cargo-topology/" + "1" * 64 + ".json",
            "sha256": "1" * 64, "size_bytes": 1,
        },
    }


_TEMPORARIES: list[tempfile.TemporaryDirectory] = []


if __name__ == "__main__":
    unittest.main()
