from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.context_plan_indexes import (
    _publish_staged_catalogs,
)


class ProjectMigrationContextPlanStagingTests(unittest.TestCase):
    def test_corrupt_staging_never_reaches_final_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-plan-staging-") as temporary:
            root = Path(temporary)
            staging, output = root / "staging", root / "output"
            relative = "context/catalog/groups/group.json"
            target = staging / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(b"corrupt")
            expected = b"expected"
            reference = {
                "path": relative,
                "sha256": hashlib.sha256(expected).hexdigest(),
                "size_bytes": len(expected),
            }

            with self.assertRaisesRegex(ValueError, "staged context catalog drifted"):
                _publish_staged_catalogs(
                    staging, out_root=output, references=[reference],
                )

            self.assertFalse((output / relative).exists())


if __name__ == "__main__":
    unittest.main()
