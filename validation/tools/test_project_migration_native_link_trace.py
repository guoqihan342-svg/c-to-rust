from __future__ import annotations

import copy
import hashlib
import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_link_trace import (
    MAX_CARGO_JSON_LINE_BYTES,
    MAX_CARGO_LINKER_TRACE_BYTES,
    MAX_LINKER_TRACE_LINE_BYTES,
    CargoLinkerTraceError,
    parse_cargo_linker_trace,
    validate_cargo_linker_trace,
)


class ProjectMigrationNativeLinkTraceTests(unittest.TestCase):
    def test_parses_one_trusted_diagnostic_with_canonical_hashes(self) -> None:
        data = _cargo_stream(_linker_message("/usr/lib/crt1.o"), _finished())

        result = parse_cargo_linker_trace(data)

        self.assertEqual({
            "schema_version", "diagnostic_count", "entries",
            "entry_set_sha256", "source_sha256", "semantic_gate",
        }, set(result))
        self.assertEqual(1, result["diagnostic_count"])
        self.assertEqual(
            [{
                "ordinal": 0, "diagnostic_ordinal": 0, "link_ordinal": 0,
                "path": "/usr/lib/crt1.o",
            }], result["entries"],
        )
        self.assertEqual(content_sha256(result["entries"]), result["entry_set_sha256"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), result["source_sha256"])
        self.assertFalse(result["semantic_gate"])
        self.assertNotIn("resolved", json.dumps(result, sort_keys=True))

    def test_multiple_diagnostics_preserve_archive_members_and_duplicates(self) -> None:
        repeated = "/toolchain/lib/libgeneric.a(member.o)"
        data = _cargo_stream(
            _linker_message(f"{repeated}\n{repeated}\n/lib64/loader.so\n"),
            _linker_message("/runtime/target/debug/deps/native.o"),
            _finished(),
        )

        result = parse_cargo_linker_trace(data)

        self.assertEqual(2, result["diagnostic_count"])
        self.assertEqual([
            {"ordinal": 0, "diagnostic_ordinal": 0, "link_ordinal": 0,
             "path": "/toolchain/lib/libgeneric.a",
             "archive_member": "member.o"},
            {"ordinal": 1, "diagnostic_ordinal": 0, "link_ordinal": 1,
             "path": "/toolchain/lib/libgeneric.a",
             "archive_member": "member.o"},
            {"ordinal": 2, "diagnostic_ordinal": 0, "link_ordinal": 2,
             "path": "/lib64/loader.so"},
            {"ordinal": 3, "diagnostic_ordinal": 1, "link_ordinal": 0,
             "path": "/runtime/target/debug/deps/native.o"},
        ], result["entries"])

    def test_requires_strict_utf8_and_strict_json_objects(self) -> None:
        invalid_inputs = (
            b"\xff",
            b"[]\n" + _cargo_stream(_finished()),
            b'{"reason":"compiler-artifact","reason":"build-finished"}\n',
        )
        for data in invalid_inputs:
            with self.subTest(data=data[:32]):
                with self.assertRaises(CargoLinkerTraceError):
                    parse_cargo_linker_trace(data)

    def test_rejects_nul_and_control_characters_in_trace_body(self) -> None:
        for character in ("\x00", "\x01", "\x7f", "\t"):
            with self.subTest(character=repr(character)):
                data = _cargo_stream(
                    _linker_message(f"/usr/lib/a{character}.o"), _finished(),
                )
                with self.assertRaisesRegex(ValueError, "control_character"):
                    parse_cargo_linker_trace(data)

    def test_plain_test_output_is_allowed_only_after_build_finished(self) -> None:
        valid = _cargo_stream(
            _linker_message("/workspace/target/debug/app"),
            _finished(),
            tail=("running 1 test", "test result: ok"),
        )
        self.assertEqual(1, len(parse_cargo_linker_trace(valid)["entries"]))

        invalid = b"running 1 test\n" + _cargo_stream(
            _linker_message("/usr/lib/a.o"), _finished(),
        )
        with self.assertRaisesRegex(ValueError, "json_invalid"):
            parse_cargo_linker_trace(invalid)

    def test_post_finish_forged_diagnostic_is_ignored(self) -> None:
        data = _cargo_stream(
            _linker_message("/usr/lib/real.o"),
            _finished(),
            _linker_message("/usr/lib/forged.o"),
            tail=("{not JSON test output",),
        )

        result = parse_cargo_linker_trace(data)

        self.assertEqual(
            [{
                "ordinal": 0, "diagnostic_ordinal": 0, "link_ordinal": 0,
                "path": "/usr/lib/real.o",
            }], result["entries"],
        )
        self.assertEqual(1, result["diagnostic_count"])

    def test_rejects_relative_traversing_and_non_guest_paths(self) -> None:
        paths = (
            "usr/lib/a.o",
            "/usr/../../private/a.o",
            "/opt/lib/a.o",
            "/runtime/private/a.o",
            "/workspace/target/C:/private/a.o",
            "/workspace/target/C:private/a.o",
            "/usr/lib\\host.o",
            "//usr/lib/a.o",
        )
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "guest_(?:path|root)"):
                    parse_cargo_linker_trace(
                        _cargo_stream(_linker_message(path), _finished())
                    )

    def test_normalizes_paths_that_remain_inside_an_allowed_root(self) -> None:
        result = parse_cargo_linker_trace(_cargo_stream(
            _linker_message("/usr/lib/gcc/../example.o"),
            _finished(),
        ))
        self.assertEqual(
            "/usr/lib/example.o", result["entries"][0]["path"],
        )

    def test_rejects_unsafe_archive_members(self) -> None:
        values = (
            "/usr/lib/a.a(../member.o)",
            "/usr/lib/a.a(/workspace/target/member.o)",
            "/usr/lib/a.a(C:/member.o)",
            "/usr/lib/a.a(C:member.o)",
            "/usr/lib/a.a(.)",
            "/usr/lib/a.a()",
            "/usr/lib/a.a(member.o",
        )
        for value in values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "archive_member"):
                    parse_cargo_linker_trace(
                        _cargo_stream(_linker_message(value), _finished())
                    )

    def test_requires_one_successful_build_finished_after_evidence(self) -> None:
        diagnostic = _linker_message("/usr/lib/a.o")
        cases = {
            "missing": _cargo_stream(diagnostic),
            "failed": _cargo_stream(diagnostic, _finished(False)),
            "multiple": _cargo_stream(diagnostic, _finished(), _finished()),
            "diagnostic-after-finish": _cargo_stream(_finished(), diagnostic),
        }
        for label, data in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(CargoLinkerTraceError):
                    parse_cargo_linker_trace(data)

    def test_rejects_wrong_code_level_prefix_stderr_and_empty_body(self) -> None:
        cases = (
            _linker_message("/usr/lib/a.o", code="other"),
            _linker_message("/usr/lib/a.o", level="note"),
            _linker_message("/usr/lib/a.o", prefix="trace: "),
            _linker_message("/usr/lib/a.o", prefix="linker stderr: "),
            _linker_message(""),
        )
        for event in cases:
            with self.subTest(message=event["message"]["message"]):
                with self.assertRaises(CargoLinkerTraceError):
                    parse_cargo_linker_trace(_cargo_stream(event, _finished()))

    def test_rejects_total_json_line_and_trace_line_overflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "input_limit"):
            parse_cargo_linker_trace(b"x" * (MAX_CARGO_LINKER_TRACE_BYTES + 1))

        json_overflow = _cargo_stream(
            _linker_message("/usr/" + "x" * MAX_CARGO_JSON_LINE_BYTES),
            _finished(),
        )
        with self.assertRaisesRegex(ValueError, "json_line_limit"):
            parse_cargo_linker_trace(json_overflow)

        trace_overflow = _cargo_stream(
            _linker_message("/usr/" + "x" * MAX_LINKER_TRACE_LINE_BYTES),
            _finished(),
        )
        with self.assertRaisesRegex(ValueError, "trace_line_limit"):
            parse_cargo_linker_trace(trace_overflow)

        post_finish_overflow = _cargo_stream(
            _linker_message("/usr/lib/a.o"), _finished(),
            tail=("x" * (MAX_CARGO_JSON_LINE_BYTES + 1),),
        )
        with self.assertRaisesRegex(ValueError, "json_line_limit"):
            parse_cargo_linker_trace(post_finish_overflow)

    def test_output_is_deterministic_and_reparse_detects_tampering(self) -> None:
        data = _cargo_stream(
            _linker_message("/usr/lib/a.o\n/lib/b.o"), _finished(),
        )
        first = parse_cargo_linker_trace(data)
        self.assertEqual(first, parse_cargo_linker_trace(data))
        self.assertEqual(first, validate_cargo_linker_trace(first, data))

        stale_hash = copy.deepcopy(first)
        stale_hash["entries"][0]["path"] = "/usr/lib/changed.o"
        with self.assertRaisesRegex(ValueError, "entry_set_sha256_drift"):
            validate_cargo_linker_trace(stale_hash)

        rebound_forgery = copy.deepcopy(stale_hash)
        rebound_forgery["entry_set_sha256"] = content_sha256(
            rebound_forgery["entries"]
        )
        with self.assertRaisesRegex(ValueError, "source_reparse_drift"):
            validate_cargo_linker_trace(rebound_forgery, data)

        source_forgery = {**first, "source_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "source_reparse_drift"):
            validate_cargo_linker_trace(source_forgery, data)


def _linker_message(
    body: str, *, code: str = "linker_messages", level: str = "warning",
    prefix: str = "linker stdout: ",
) -> dict:
    return {
        "reason": "compiler-message",
        "message": {
            "code": {"code": code, "explanation": None},
            "level": level,
            "message": prefix + body,
            "children": [],
            "rendered": "warning: diagnostic rendering is not evidence",
        },
    }


def _finished(success: bool = True) -> dict:
    return {"reason": "build-finished", "success": success}


def _cargo_stream(*events: dict, tail: tuple[str, ...] = ()) -> bytes:
    lines = [
        json.dumps(event, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        for event in events
    ]
    lines.extend(tail)
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


if __name__ == "__main__":
    unittest.main()
