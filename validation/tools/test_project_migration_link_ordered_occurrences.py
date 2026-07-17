from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.archive_closure import (
    parse_archive_command,
)
from validation.tools._project_migration_harness.link_closure import (
    _parse_link_argv,
)


class LinkOrderedOccurrenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="link-occurrences-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.base = self.root / "build"
        self.base.mkdir()
        for name, payload in (
            ("first.o", b"first"),
            ("second.o", b"second"),
            ("program", b"program"),
        ):
            (self.base / name).write_bytes(payload)
        for name in ("lib-a", "lib-b"):
            (self.base / name).mkdir()
        self.fact = {"path": "build/CMakeFiles/sample.dir/link.txt"}

    def test_cross_category_order_uses_output_elided_semantic_indexes(self) -> None:
        external = "/outside/private/libalpha.so.3"
        target, blockers = _parse_link_argv(
            self.root,
            self.base,
            self.fact,
            [
                "clang", "first.o", "-o", "program", "-L", "lib-a",
                "-lz", external, "second.o", "-Llib-b", "-pthread",
                "first.o", "-L", "lib-a", "-lz", external,
            ],
        )

        self.assertEqual([], blockers)
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(
            ["build/first.o", "build/second.o", "build/first.o"],
            [item["path"] for item in target["inputs"]],
        )
        self.assertEqual(
            ["build/lib-a", "build/lib-b", "build/lib-a"],
            [item["path"] for item in target["search_roots"]],
        )
        self.assertEqual(
            ["-lz", "-pthread", "-lz"],
            target["ordered_system_link_args"],
        )
        self.assertEqual(
            ["libalpha.so.3", "libalpha.so.3"],
            [item["name"] for item in target["external_native_libraries"]],
        )
        self.assertEqual(
            [4, 12],
            [
                item["argument_index"]
                for item in target["external_native_libraries"]
            ],
        )
        self.assertEqual([
            _occurrence(0, 0, 1, "input", 0),
            _occurrence(1, 1, 2, "search-root", 0),
            _occurrence(2, 3, 1, "system-argument", 0),
            _occurrence(3, 4, 1, "external-native-library", 0),
            _occurrence(4, 5, 1, "input", 1),
            _occurrence(5, 6, 1, "search-root", 1),
            _occurrence(6, 7, 1, "system-argument", 1),
            _occurrence(7, 8, 1, "input", 2),
            _occurrence(8, 9, 2, "search-root", 2),
            _occurrence(9, 11, 1, "system-argument", 2),
            _occurrence(10, 12, 1, "external-native-library", 1),
        ], target["ordered_link_occurrences"])
        self._assert_references_are_bijective(target)
        self.assertNotIn(external, json.dumps(target, sort_keys=True))

    def test_unsupported_argument_is_a_gap_not_an_occurrence(self) -> None:
        unsupported = "-Wl,-T/outside/private/secret.ld"
        target, blockers = _parse_link_argv(
            self.root,
            self.base,
            self.fact,
            ["clang", "-o", "program", "first.o", unsupported, "-lz"],
        )

        self.assertIsNotNone(target)
        assert target is not None
        self.assertIn("external_link_argument", {
            item["kind"] for item in blockers
        })
        self.assertEqual([
            _occurrence(0, 0, 1, "input", 0),
            _occurrence(1, 2, 1, "system-argument", 0),
        ], target["ordered_link_occurrences"])
        self.assertNotIn(
            unsupported,
            json.dumps({"target": target, "blockers": blockers}, sort_keys=True),
        )

    def _assert_references_are_bijective(self, target: dict) -> None:
        categories = {
            "input": "inputs",
            "search-root": "search_roots",
            "system-argument": "ordered_system_link_args",
            "external-native-library": "external_native_libraries",
        }
        for kind, key in categories.items():
            references = [
                item["reference_ordinal"]
                for item in target["ordered_link_occurrences"]
                if item["kind"] == kind
            ]
            self.assertEqual(list(range(len(target[key]))), references)


class ArchiveOrderedOccurrenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="archive-occurrences-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.base = self.root / "build"
        self.base.mkdir()
        for name in (
            "right.o", "left.o", "left.obj", "right.obj",
            "libsample.a", "sample.lib",
        ):
            (self.base / name).write_bytes(name.encode("ascii"))
        self.fact = {"path": "build/archive-command.txt"}

    def test_gnu_archive_indexes_elide_output_and_preserve_member_order(self) -> None:
        target, blockers = parse_archive_command(
            self.root,
            self.base,
            self.fact,
            ["ar", "qc", "libsample.a", "right.o", "left.o", "right.o"],
        )

        self.assertEqual([], blockers)
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual([
            _occurrence(0, 1, 1, "input", 0),
            _occurrence(1, 2, 1, "input", 1),
            _occurrence(2, 3, 1, "input", 2),
        ], target["ordered_link_occurrences"])
        self.assertEqual(
            ["build/right.o", "build/left.o", "build/right.o"],
            [item["path"] for item in target["inputs"]],
        )

    def test_msvc_archive_indexes_elide_out_but_retain_nologo_gap(self) -> None:
        target, blockers = parse_archive_command(
            self.root,
            self.base,
            self.fact,
            [
                "lib.exe", "/NOLOGO", "left.obj", "/OUT:sample.lib",
                "right.obj", "left.obj",
            ],
        )

        self.assertEqual([], blockers)
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual("msvc-lib", target["archive_operation"])
        self.assertEqual([
            _occurrence(0, 1, 1, "input", 0),
            _occurrence(1, 2, 1, "input", 1),
            _occurrence(2, 3, 1, "input", 2),
        ], target["ordered_link_occurrences"])
        self.assertEqual(
            ["build/left.obj", "build/right.obj", "build/left.obj"],
            [item["path"] for item in target["inputs"]],
        )

    def test_unsupported_archive_input_does_not_create_a_target(self) -> None:
        target, blockers = parse_archive_command(
            self.root,
            self.base,
            self.fact,
            ["ar", "qc", "libsample.a", "right.o", "--plugin=secret"],
        )

        self.assertIsNone(target)
        self.assertEqual(
            {"archive_input_argument_unsupported"},
            {item["kind"] for item in blockers},
        )


def _occurrence(
    ordinal: int,
    argument_index: int,
    argument_count: int,
    kind: str,
    reference_ordinal: int,
) -> dict[str, int | str]:
    return {
        "ordinal": ordinal,
        "argument_index": argument_index,
        "argument_count": argument_count,
        "kind": kind,
        "reference_ordinal": reference_ordinal,
    }


if __name__ == "__main__":
    unittest.main()
