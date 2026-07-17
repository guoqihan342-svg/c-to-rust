from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.make_dry_run_parser import (
    MakeDryRunParseError, parse_make_dry_run_stdout,
)


class MakeArchiveArgvTests(unittest.TestCase):
    archive = "output/generic/libunit.a"
    member = "output/generic/unit.o"

    def test_accepts_only_provable_creation_modes(self) -> None:
        for mode in ("r", "q", "rcsDv", "qcSDv", "-rcv"):
            with self.subTest(mode=mode):
                parsed = parse_make_dry_run_stdout(
                    f"ar {mode} {self.archive} {self.member}\n"
                )
                command = parsed["commands"][0]
                self.assertEqual("archive", command["kind"])
                self.assertEqual([self.member], command["inputs"])
                self.assertEqual([self.archive], command["outputs"])

    def test_rejects_ambiguous_duplicate_or_unsupported_modes(self) -> None:
        modes = (
            "cDs", "rq", "rr", "qq", "rsS", "rcc", "rss", "rDD", "rvv",
            "rP", "rU", "ru", "ra", "rm",
        )
        for mode in modes:
            with self.subTest(mode=mode), self.assertRaisesRegex(
                MakeDryRunParseError, "archive_mode_unsupported",
            ):
                parse_make_dry_run_stdout(
                    f"ar {mode} {self.archive} {self.member}\n"
                )

    def test_requires_at_least_one_member(self) -> None:
        for mode in ("rcs", "qS"):
            with self.subTest(mode=mode), self.assertRaisesRegex(
                MakeDryRunParseError, "archive_member_missing",
            ):
                parse_make_dry_run_stdout(f"ar {mode} {self.archive}\n")

    def test_rejects_options_as_output_or_members(self) -> None:
        cases = (
            (f"ar rcs --thin {self.archive} {self.member}", "archive_output_unsupported"),
            (f"ar rcs --plugin=evil.so {self.archive} {self.member}", "archive_output_unsupported"),
            (f"ar rcs {self.archive} --thin {self.member}", "archive_member_unsupported"),
            (f"ar rcs {self.archive} --plugin=evil.so {self.member}", "archive_member_unsupported"),
            (f"ar rcs ../outside.a {self.member}", "path_escape"),
        )
        for stdout, reason in cases:
            with self.subTest(stdout=stdout), self.assertRaisesRegex(
                MakeDryRunParseError, reason,
            ):
                parse_make_dry_run_stdout(stdout + "\n")


if __name__ == "__main__":
    unittest.main()
