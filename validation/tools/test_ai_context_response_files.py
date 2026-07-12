from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts import context_response_files as response_files


class AiContextResponseFileTests(unittest.TestCase):
    def expand(self, root: Path, argv: list[str], *, compiler: str = "clang"):
        build = root / "build"
        build.mkdir(exist_ok=True)
        return response_files.expand_response_files(
            argv,
            source_root=root,
            working_directory=build,
            compiler=compiler,
        )

    def test_gnu_quoting_is_expanded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build").mkdir()
            (root / "build/flags.rsp").write_text(
                '-DNAME="value with spaces" -I"../include dir" -IC:\\sdk\\include -include ""',
                encoding="utf-8",
            )
            expanded, report = self.expand(root, ["clang", "@flags.rsp"])
            self.assertEqual(
                [
                    "clang",
                    "-DNAME=value with spaces",
                    "-I../include dir",
                    "-IC:\\sdk\\include",
                    "-include",
                    "",
                ],
                expanded,
            )
            self.assertEqual("gnu-v1", report["dialect"])

    def test_msvc_and_unknown_dialects_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build").mkdir()
            (root / "build/flags.rsp").write_text("-DVALUE=1", encoding="utf-8")
            for compiler in ("cl.exe", "custom-compiler", "customclang"):
                with self.subTest(compiler=compiler):
                    expanded, report = self.expand(root, [compiler, "@flags.rsp"], compiler=compiler)
                    self.assertIsNone(expanded)
                    self.assertEqual("response_file_dialect_unsupported", report["reason"])

    def test_initial_argument_overflow_is_not_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            response_files,
            "MAX_EXPANDED_ARGUMENTS",
            2,
        ):
            expanded, report = self.expand(Path(tmp), ["clang", "-c", "unit.c"])
            self.assertIsNone(expanded)
            self.assertEqual("initial_argument_count_exceeded", report["reason"])

    def test_repeated_reference_consumes_file_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build").mkdir()
            (root / "build/flags.rsp").write_text("-DVALUE=1", encoding="utf-8")
            with mock.patch.object(response_files, "MAX_RESPONSE_FILES", 1):
                expanded, report = self.expand(root, ["clang", "@flags.rsp", "@flags.rsp"])
            self.assertIsNone(expanded)
            self.assertEqual("response_file_count_exceeded", report["reason"])
            self.assertEqual(2, report["expansion_count"])
            self.assertEqual(1, report["unique_file_count"])

    def test_invalid_encoding_nul_and_quotes_fail_closed(self) -> None:
        cases = {
            "encoding": (b"\xff", "response_file_encoding_invalid"),
            "nul": (b"-DVALUE=1\x00", "response_file_nul_invalid"),
            "quote": (b"-DVALUE='unterminated", "response_file_parse_invalid"),
        }
        for name, (data, reason) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "build").mkdir()
                (root / "build/flags.rsp").write_bytes(data)
                expanded, report = self.expand(root, ["clang", "@flags.rsp"])
                self.assertIsNone(expanded)
                self.assertEqual(reason, report["reason"])

    def test_symlink_response_file_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build"
            build.mkdir()
            target = root / "target.rsp"
            target.write_text("-DVALUE=1", encoding="utf-8")
            link = build / "flags.rsp"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlink creation unavailable")
            expanded, report = self.expand(root, ["clang", "@flags.rsp"])
            self.assertIsNone(expanded)
            self.assertEqual("response_file_path_outside_source_root", report["reason"])


if __name__ == "__main__":
    unittest.main()
