from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools import project_migration_harness
from validation.tools._project_migration_harness.project_migration_cli import parse_args
from validation.tools._project_migration_harness.project_test_target_proposal import (
    load_project_test_target_proposal,
    resolve_project_test_target_proposal_selection,
)


class MakeTargetProposalCliTests(unittest.TestCase):
    def test_materializer_emits_reusable_bound_migrate_arguments(self) -> None:
        with tempfile.TemporaryDirectory(prefix="make-proposal-cli-") as temporary:
            root = Path(temporary)
            output = io.StringIO()
            with (
                patch.object(project_migration_harness, "REPO_ROOT", root),
                redirect_stdout(output),
            ):
                code = project_migration_harness.main([
                    "prepare-make-test-target-proposal",
                    "--target", "verify-core",
                    "--provider", "neutral-provider",
                    "--model", "neutral-model",
                    "--prompt-sha256", "a" * 64,
                    "--response-sha256", "b" * 64,
                    "--out-root", "target/proposal-input",
                ])

            self.assertEqual(0, code)
            result = json.loads(output.getvalue())
            self.assertEqual("materialized", result["status"])
            path = root / Path(*result["proposal"]["path"].split("/"))
            data = path.read_bytes()
            self.assertEqual(
                hashlib.sha256(data).hexdigest(), result["proposal"]["sha256"],
            )
            parsed = parse_args([
                "migrate", "--repo-root", str(root),
                *result["migrate_arguments"],
            ])
            bound = load_project_test_target_proposal(
                resolve_project_test_target_proposal_selection(
                    parsed.project_test_target_proposal, harness_root=root,
                ),
            )
            self.assertEqual("verify-core", bound["proposal"]["target"])


if __name__ == "__main__":
    unittest.main()
