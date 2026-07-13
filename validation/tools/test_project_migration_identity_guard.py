from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.identity_guard import (
    scan_identity_dispatch,
)


class ProjectMigrationIdentityGuardTests(unittest.TestCase):
    def test_production_orchestrator_has_no_known_project_dispatch(self) -> None:
        package = Path(__file__).parent / "_project_migration_harness"

        report = scan_identity_dispatch(
            package.rglob("*.py"),
            [
                "flashdb",
                "real-fdb",
                "libuv",
                "zlib",
                "kv_to_blob",
                "src/fdb",
            ],
        )

        self.assertEqual("passed", report["status"], report["findings"])
        self.assertGreater(report["files_scanned"], 20)

    def test_renamed_generic_policy_has_no_identity_finding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-identity-neutral-") as tmp:
            source = Path(tmp) / "policy.py"
            source.write_text(
                "def select_route(facts):\n"
                "    return 'context_group' if facts['has_cycle'] else 'independent'\n",
                encoding="utf-8",
            )

            report = scan_identity_dispatch([source], ["sample-one", "vendor/two"])

        self.assertEqual("passed", report["status"])
        self.assertEqual([], report["findings"])

    def test_project_and_path_literal_dispatch_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-identity-dispatch-") as tmp:
            source = Path(tmp) / "policy.py"
            source.write_text(
                "def select_route(project):\n"
                "    if project == 'sample-one':\n"
                "        return 'special'\n"
                "    return 'src/vendor/two/unit.c'\n",
                encoding="utf-8",
            )

            report = scan_identity_dispatch([source], ["sample-one", "vendor/two"])

        self.assertEqual("failed", report["status"])
        self.assertEqual(2, report["finding_count"])
        self.assertEqual(
            {"sample-one", "vendor/two"},
            {item["identity"] for item in report["findings"]},
        )

    def test_bytes_concat_hash_and_agent_markdown_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-identity-encoded-") as tmp:
            root = Path(tmp)
            source = root / "policy.py"
            digest = hashlib.sha256(b"vendor/two").hexdigest()[:16]
            source.write_text(
                "SPECIAL = b'sample-' + b'one'\n"
                f"PROJECT_HASH = '{digest}'\n",
                encoding="utf-8",
            )
            agent = root / "c2rust-candidate.md"
            agent.write_text("Use a dedicated route for vendor/three.\n", encoding="utf-8")

            report = scan_identity_dispatch(
                [source, agent], ["sample-one", "vendor/two", "vendor/three"],
            )

        self.assertEqual("failed", report["status"])
        self.assertEqual(
            {"sample-one", "vendor/two", "vendor/three"},
            {item["identity"] for item in report["findings"]},
        )


if __name__ == "__main__":
    unittest.main()
