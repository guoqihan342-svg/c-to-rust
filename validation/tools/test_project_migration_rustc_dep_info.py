from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.anchored_artifact_io import (
    open_directory_anchor,
)
from validation.tools._project_migration_harness.cargo_rustc_dep_info_capture import (
    capture_cargo_rustc_dep_info,
)
from validation.tools._project_migration_harness.rustc_dep_info import (
    parse_rustc_dep_info, validate_rustc_dep_info,
)
from validation.tools._project_migration_harness.rustc_dep_info_evidence import (
    persist_captured_rustc_dep_info, read_rustc_dep_info,
    validate_rustc_dep_info_evidence,
)
from validation.tools.project_migration_rust_cargo_link_order_test_support import (
    cargo_stream,
)


PRODUCT = "/runtime/target/debug/libstatic_target.a"
SOURCES = (
    "/workspace/packages/static/src/lib.rs",
    "/workspace/packages/static/src/modules/first.rs",
    "/workspace/packages/static/src/modules/second.rs",
)


def dep_info(*sources: str) -> bytes:
    return f"{PRODUCT}: {' '.join(sources)}\n\n".encode("utf-8")


class RustcDepInfoTests(unittest.TestCase):
    def test_parser_preserves_source_order_and_reparses(self) -> None:
        raw = dep_info(*SOURCES)
        facts = parse_rustc_dep_info(raw)
        self.assertEqual(3, facts["source_count"])
        self.assertEqual([0, 1, 2], [item["ordinal"] for item in facts["sources"]])
        self.assertEqual(facts, validate_rustc_dep_info(facts, raw))

    def test_parser_rejects_duplicate_escape_and_target_drift(self) -> None:
        cases = (
            dep_info(SOURCES[0], SOURCES[0]),
            dep_info("/workspace/../outside.rs"),
            b"/workspace/not-target: /workspace/source.rs\n",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_rustc_dep_info(raw)

    def test_capture_persist_and_reopen_are_content_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "execution" / "target"
            dep_path = target / "debug" / "libstatic_target.d"
            dep_path.parent.mkdir(parents=True)
            dep_path.write_bytes(dep_info(*SOURCES))
            anchor = open_directory_anchor(target.resolve(strict=True))
            try:
                captured = capture_cargo_rustc_dep_info(
                    {"status": "passed", "_captured_stdout": cargo_stream(
                        static_only=True,
                    )},
                    root / "execution", target_anchor=anchor,
                )
            finally:
                anchor.close()
            out_root = root / "artifacts"
            (out_root / "state").mkdir(parents=True)
            ledger = out_root / "state" / "project-migration.sqlite3"
            ledger.write_bytes(b"")
            execution = persist_captured_rustc_dep_info(
                {"status": "passed", "_captured_rustc_dep_info": captured},
                out_root=out_root, required=True,
            )
            self.assertEqual("passed", execution["status"])
            self.assertEqual(1, len(execution["rustc_dep_info"]))
            evidence = execution["rustc_dep_info"][0]
            raw, facts = read_rustc_dep_info(ledger, evidence)
            self.assertEqual(dep_info(*SOURCES), raw)
            self.assertEqual(evidence["facts"], facts)

            forged = copy.deepcopy(evidence)
            forged["facts"]["sources"].reverse()
            with self.assertRaises(ValueError):
                validate_rustc_dep_info_evidence(forged)

    def test_required_capture_absence_blocks(self) -> None:
        result = persist_captured_rustc_dep_info(
            {"status": "passed"}, out_root=Path.cwd(), required=True,
        )
        self.assertEqual("blocked", result["status"])
        self.assertEqual([], result["rustc_dep_info"])


if __name__ == "__main__":
    unittest.main()
