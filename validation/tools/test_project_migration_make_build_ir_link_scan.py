from __future__ import annotations

from pathlib import Path
import unittest

from validation.tools._project_migration_harness.make_build_ir_link_scan import (
    scan_make_archive, scan_make_link,
)


class MakeBuildIRLinkScanTests(unittest.TestCase):
    def test_cross_category_order_survives_output_elision(self) -> None:
        target = _target("link", ["obj/unit.o"], "bin/app")
        command = _command(
            "link",
            [
                "cc", "-Wl,--as-needed", "obj/unit.o", "-L", "lib",
                "-lm", "--output=bin/app",
            ],
            ["obj/unit.o"], "bin/app",
        )
        raw, resolution = scan_make_link(
            Path("."), command, target, {"working_directory": "."},
        )
        self.assertEqual(
            ["system-argument", "input", "search-root", "system-argument"],
            [item["kind"] for item in raw["ordered_link_occurrences"]],
        )
        self.assertEqual([0, 1, 2, 4], [
            item["argument_index"] for item in raw["ordered_link_occurrences"]
        ])
        self.assertEqual(
            ["-Wl,--as-needed", "-lm"], raw["ordered_system_link_args"],
        )
        self.assertEqual(False, raw["search_roots"][0]["materialized"])
        self.assertEqual([2, 4], [item["ordinal"] for item in resolution])

    def test_forwarded_search_root_is_one_bound_occurrence(self) -> None:
        target = _target("link", ["obj/unit.o"], "bin/app")
        command = _command(
            "link",
            ["cc", "obj/unit.o", "-Wl,-L,lib", "-lunit", "-o", "bin/app"],
            ["obj/unit.o"], "bin/app",
        )
        raw, _resolution = scan_make_link(
            Path("."), command, target, {"working_directory": "."},
        )
        root = next(
            item for item in raw["ordered_link_occurrences"]
            if item["kind"] == "search-root"
        )
        self.assertEqual((1, 1), (
            root["argument_index"], root["argument_count"],
        ))
        self.assertEqual("lib", raw["search_roots"][0]["path"])

    def test_path_bearing_or_drifted_link_arguments_fail_closed(self) -> None:
        target = _target("link", ["obj/unit.o"], "bin/app")
        cases = (
            [
                "cc", "obj/unit.o", "-Wl,--version-script=config/map.ld",
                "-o", "bin/app",
            ],
            ["cc", "obj/other.o", "-o", "bin/app"],
            ["cc", "obj/unit.o", "-o", "bin/other"],
        )
        for argv in cases:
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                scan_make_link(
                    Path("."),
                    _command("link", argv, ["obj/unit.o"], "bin/app"),
                    target,
                    {"working_directory": "."},
                )

    def test_archive_mode_is_separate_from_ordered_members(self) -> None:
        target = _target("archive", ["obj/a.o", "obj/b.o"], "lib/libunit.a")
        command = _command(
            "archive",
            ["ar", "rcs", "lib/libunit.a", "obj/a.o", "obj/b.o"],
            ["obj/a.o", "obj/b.o"], "lib/libunit.a",
        )
        raw, resolution = scan_make_archive(
            command, target, {"working_directory": "."},
        )
        self.assertEqual([], resolution)
        self.assertEqual([1, 2], [
            item["argument_index"] for item in raw["ordered_link_occurrences"]
        ])
        self.assertEqual(
            ["input", "input"],
            [item["kind"] for item in raw["ordered_link_occurrences"]],
        )

    def test_archive_argv_rejects_options_duplicate_modes_and_empty_members(self) -> None:
        cases = (
            (["ar", "rcs", "--thin", "lib/libunit.a", "obj/a.o"], ["obj/a.o"]),
            (["ar", "rcs", "--plugin=evil.so", "lib/libunit.a", "obj/a.o"], ["obj/a.o"]),
            (["ar", "rcs", "lib/libunit.a", "--thin", "obj/a.o"], ["obj/a.o"]),
            (["ar", "rcs", "lib/libunit.a", "--plugin=evil.so", "obj/a.o"], ["obj/a.o"]),
            (["ar", "rccs", "lib/libunit.a", "obj/a.o"], ["obj/a.o"]),
            (["ar", "rcs", "lib/libunit.a"], []),
        )
        for argv, inputs in cases:
            with self.subTest(argv=argv), self.assertRaisesRegex(
                ValueError, "make_build_ir_archive_argv_invalid",
            ):
                scan_make_archive(
                    _command("archive", argv, inputs, "lib/libunit.a"),
                    _target("archive", inputs, "lib/libunit.a"),
                    {"working_directory": "."},
                )


def _target(kind: str, inputs: list[str], output: str) -> dict:
    return {
        "target_id": f"target-{kind}",
        "kind": kind,
        "outputs": [_binding(output)],
        "ordered_inputs": [
            {
                "ordinal": ordinal, "role": "link-input",
                "binding": _binding(path),
                "dependency_target_id": f"producer-{ordinal}",
            }
            for ordinal, path in enumerate(inputs)
        ],
    }


def _binding(path: str) -> dict:
    return {"path": path, "kind": "file", "materialized": False}


def _command(
    kind: str, argv: list[str], inputs: list[str], output: str,
) -> dict:
    return {
        "ordinal": 0, "kind": kind, "argv": argv,
        "inputs": inputs, "outputs": [output],
    }


if __name__ == "__main__":
    unittest.main()
