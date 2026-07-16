from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.project_test_inventory_make import (
    collect_make_test_dry_run, inventory_from_make_observation,
)


LIVE = os.environ.get("C2R_RUN_LIVE_TOOLCHAIN_TESTS") == "1"


@unittest.skipUnless(LIVE, "set C2R_RUN_LIVE_TOOLCHAIN_TESTS=1")
class MakeProjectTestInventoryLiveTests(unittest.TestCase):
    def test_linux_bubblewrap_collects_explicit_make_test_recipe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="make-test-inventory-live-") as raw:
            root = Path(raw)
            build = root / "build"
            build.mkdir()
            executable = build / "suite-bin"
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            (build / "Makefile").write_text(
                ".PHONY: test\n"
                "test:\n"
                "\t@echo preparing\n"
                "\t./suite-bin --strict\n",
                encoding="ascii",
            )

            collected = collect_make_test_dry_run(root, build)
            self.assertEqual("collected", collected["status"], collected)
            data = executable.read_bytes()
            build_ir = {"targets": [{
                "target_id": "link-target", "kind": "link",
                "outputs": [{
                    "path": "build/suite-bin", "kind": "file",
                    "materialized": True,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }],
            }]}
            inventory = inventory_from_make_observation(
                root, build_ir, collected["observation"],
                source_observation={
                    "path": "plan/make-observation.json",
                    "sha256": "a" * 64,
                    "size_bytes": 1,
                },
            )

            self.assertEqual("ready", inventory["status"], inventory)
            self.assertEqual("make-dry-run-v1", inventory["adapter"])
            self.assertEqual("link-target", inventory["tests"][0]["source_target_id"])
            self.assertEqual(
                [{"kind": "literal", "value": "--strict"}],
                inventory["tests"][0]["arguments"],
            )


if __name__ == "__main__":
    unittest.main()
