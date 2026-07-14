from __future__ import annotations

import gc
from pathlib import Path
import tempfile
import tracemalloc
import unittest

from validation.tools._project_migration_harness.artifacts import (
    write_json_artifact,
)
from validation.tools._project_migration_harness.ledger_run_metadata import (
    _bound_portfolio,
)


class ProjectMigrationLedgerMetadataStreamingTests(unittest.TestCase):
    def test_in_memory_portfolio_binding_does_not_allocate_full_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ledger-metadata-stream-") as temporary:
            output = Path(temporary)
            database = output / "state/project-migration.sqlite3"
            portfolio = {
                "run_id": "run", "dag_sha256": "d" * 64,
                "payload": "x" * (8 * 1024 * 1024),
            }
            reference = write_json_artifact(
                output, "plan/portfolio.json", portfolio,
            )

            gc.collect()
            tracemalloc.start()
            try:
                rebound = _bound_portfolio(
                    database, reference, portfolio_payload=portfolio,
                )
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()

            self.assertIs(portfolio, rebound)
            self.assertLess(peak, 3 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
