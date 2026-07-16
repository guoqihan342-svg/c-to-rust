from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from validation.tools._project_migration_harness.project_test_inventory_meson import (
    collect_meson_test_introspection,
)
from validation.tools._project_migration_harness.project_test_inventory_meson_parse import (
    inventory_from_meson_observation,
)


LIVE = (
    os.environ.get("C2R_RUN_LIVE_TOOLCHAIN_TESTS") == "1"
    and sys.platform == "linux"
    and shutil.which("meson") is not None
    and shutil.which("bwrap") is not None
)


@unittest.skipUnless(
    LIVE, "set C2R_RUN_LIVE_TOOLCHAIN_TESTS=1 with meson and bwrap",
)
class MesonProjectTestInventoryLiveTests(unittest.TestCase):
    def test_real_meson_introspection_is_read_only_and_maps_direct_test(self) -> None:
        with tempfile.TemporaryDirectory(prefix="meson-test-inventory-live-") as raw:
            root = Path(raw)
            (root / "meson.build").write_text(
                "project('neutral', 'c')\n"
                "suite = executable('suite-bin', 'unit.c')\n"
                "test('source-suite', suite, args: ['--probe'])\n",
                encoding="ascii",
            )
            (root / "unit.c").write_text(
                "int main(int argc, char **argv) { return argc == 2 ? 0 : 1; }\n",
                encoding="ascii",
            )
            meson = str(shutil.which("meson"))
            subprocess.run(
                [meson, "setup", "build"], cwd=root,
                check=True, capture_output=True, timeout=60,
            )
            subprocess.run(
                [meson, "compile", "-C", "build"], cwd=root,
                check=True, capture_output=True, timeout=60,
            )
            build, database = root / "build", root / "build/compile_commands.json"
            collected = collect_meson_test_introspection(root, build, database)

            self.assertEqual("collected", collected["status"], collected)
            self.assertFalse((root / "test-ran.marker").exists())
            raw_test = collected["observation"]["payload"][0]
            self.assertEqual(1, len(raw_test["depends"]), raw_test)
            executable = Path(raw_test["cmd"][0])
            data = executable.read_bytes()
            build_ir = {"targets": [{
                "target_id": "link-target", "kind": "link",
                "outputs": [{
                    "path": executable.relative_to(root).as_posix(),
                    "kind": "file", "materialized": True,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }],
                "provenance": {
                    "raw_fact_role": "generated-build-closure",
                    "meson_target_id": raw_test["depends"][0],
                },
            }]}
            inventory = inventory_from_meson_observation(
                root, build_ir, collected["observation"],
                source_observation={
                    "path": "plan/meson-observation.json",
                    "sha256": "a" * 64, "size_bytes": 1,
                },
            )

            self.assertEqual("ready", inventory["status"], inventory)
            self.assertEqual("link-target", inventory["tests"][0]["source_target_id"])
            self.assertEqual(
                [{"kind": "literal", "value": "--probe"}],
                inventory["tests"][0]["arguments"],
            )


if __name__ == "__main__":
    unittest.main()
