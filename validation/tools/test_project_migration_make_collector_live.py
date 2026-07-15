from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import tempfile
import unittest

from validation.tools._project_migration_harness.make_dry_run_collect import (
    collect_make_facts,
)
from validation.tools._project_migration_harness.make_dry_run_report_io import (
    reopen_make_dry_run_report,
)


LIVE = os.environ.get("C2R_RUN_LIVE_TOOLCHAIN_TESTS") == "1"


@unittest.skipUnless(LIVE and platform.system() == "Linux", "explicit Linux live gate")
class MakeCollectorLiveTests(unittest.TestCase):
    def test_real_bubblewrap_subdirectory_make_report_reopens(self) -> None:
        missing = [name for name in ("bwrap", "make") if shutil.which(name) is None]
        self.assertEqual([], missing, f"missing make collection tools: {missing}")
        with tempfile.TemporaryDirectory(prefix="make-collector-live-") as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            self._write(root, "src/unit.c", "int unit(void) { return 11; }\n")
            self._write(root, "include/config.h", "#define UNIT_VALUE 11\n")
            self._write(root, "vendor/prebuilt.a", "bounded-input\n")
            self._write(
                root,
                "build/Makefile",
                "all: app\n"
                "obj/unit.o: ../src/unit.c\n"
                "\tcc -I../include -c ../src/unit.c -o obj/unit.o\n"
                "app: obj/unit.o ../vendor/prebuilt.a\n"
                "\tcc obj/unit.o ../vendor/prebuilt.a -o app\n",
            )

            result = collect_make_facts(
                root,
                working_directory="build",
                makefile="Makefile",
                targets=["all"],
                out_root="target/make-facts",
                timeout_seconds=30,
            )

            self.assertEqual("ready", result["status"], result)
            report = reopen_make_dry_run_report(root, result["make_report"])
            self.assertEqual("build", report["working_directory"])
            self.assertEqual(["compile", "link"], [
                command["kind"] for command in report["commands"]
            ])
            self.assertEqual(["src/unit.c", "vendor/prebuilt.a"], [
                reference["path"] for reference in report["input_refs"]
            ])
            self.assertTrue(report["repository_snapshot_ref"]["path"].startswith(
                "target/make-facts/cas/repository-snapshot/"
            ))

    def test_repository_symlink_is_rejected_before_make(self) -> None:
        with tempfile.TemporaryDirectory(prefix="make-collector-link-") as temporary:
            base = Path(temporary)
            root = base / "project"
            root.mkdir()
            self._write(root, "build/Makefile", "all:\n\tcc -c linked.c -o unit.o\n")
            outside = base / "outside.c"
            outside.write_text("int outside(void) { return 0; }\n", encoding="utf-8")
            (root / "build/linked.c").symlink_to(outside)

            result = collect_make_facts(
                root,
                working_directory="build",
                makefile="Makefile",
                targets=["all"],
                out_root="target/make-facts",
                timeout_seconds=30,
            )

            self.assertEqual("blocked", result["status"], result)
            self.assertEqual(["make_collection_snapshot_blocked"], result["blockers"])
            self.assertFalse(result["make_started"])

    @staticmethod
    def _write(root: Path, relative: str, content: str) -> None:
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
