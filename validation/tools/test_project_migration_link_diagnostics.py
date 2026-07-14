from __future__ import annotations

import json
import unittest

from validation.tools._project_migration_harness.project_cargo_diagnostic_intake import (
    partition_cargo_diagnostics,
)
from validation.tools._project_migration_harness.sandbox_diagnostics import (
    cargo_check_diagnostics, cargo_diagnostics,
)


class ProjectMigrationLinkDiagnosticTests(unittest.TestCase):
    def test_unique_project_symbol_becomes_link_repair(self) -> None:
        diagnostics = cargo_diagnostics(_linker_stdout("shared_api"), "check")
        self.assertEqual(1, len(diagnostics))
        self.assertEqual("linker-undefined-symbol", diagnostics[0]["code"])
        self.assertEqual("shared_api", diagnostics[0]["linker_symbol"])
        self.assertNotIn("private", json.dumps(diagnostics))

        partition = partition_cargo_diagnostics(
            gate_kind="cargo-check", diagnostics=diagnostics,
            candidate_members=[_member("a")],
            rust_project_ir=_ir(
                modules=[_module("a")],
                public_api=[{
                    "declaration_id": "public-shared", "module_id": "module-a",
                    "symbol": "shared_api",
                }],
            ),
        )
        self.assertIsNone(partition.admission_blocker)
        self.assertEqual({}, partition.unit_diagnostics)
        self.assertEqual("link", partition.project_diagnostics[0]["family"])
        self.assertEqual(
            ["module-a"], partition.project_diagnostics[0][
                "project_diagnostic"
            ]["affected_module_ids"],
        )

    def test_ambiguous_or_external_symbol_blocks_whole_batch(self) -> None:
        diagnostics = cargo_diagnostics(_linker_stdout("shared_api"), "check")
        cases = {
            "ambiguous": _ir(
                modules=[_module("a"), _module("b")],
                public_api=[
                    {"declaration_id": "a", "module_id": "module-a",
                     "symbol": "shared_api"},
                    {"declaration_id": "b", "module_id": "module-b",
                     "symbol": "shared_api"},
                ],
            ),
            "external-import": _ir(
                modules=[_module("a")],
                ffi_boundaries=[{
                    "declaration_id": "foreign", "module_id": "module-a",
                    "symbol": "foreign_shared", "link_name": "shared_api",
                    "direction": "import",
                }],
            ),
        }
        for label, ir in cases.items():
            with self.subTest(label=label):
                members = [_member("a"), _member("b")] \
                    if label == "ambiguous" else [_member("a")]
                partition = partition_cargo_diagnostics(
                    gate_kind="cargo-check", diagnostics=diagnostics,
                    candidate_members=members, rust_project_ir=ir,
                )
                self.assertEqual(
                    "link-symbol-not-project-unique",
                    partition.admission_blocker,
                )
                self.assertEqual([], partition.project_diagnostics)

    def test_one_unknown_link_symbol_blocks_known_symbol_too(self) -> None:
        diagnostics = cargo_diagnostics(
            _linker_stdout("shared_api", "external_missing"), "check",
        )
        partition = partition_cargo_diagnostics(
            gate_kind="cargo-check", diagnostics=diagnostics,
            candidate_members=[_member("a")],
            rust_project_ir=_ir(
                modules=[_module("a")],
                public_api=[{
                    "declaration_id": "public-shared", "module_id": "module-a",
                    "symbol": "shared_api",
                }],
            ),
        )
        self.assertEqual(
            "link-symbol-not-project-unique", partition.admission_blocker,
        )
        self.assertEqual([], partition.project_diagnostics)

    def test_linker_like_text_requires_exact_rustc_parent(self) -> None:
        stdout = _linker_stdout(
            "shared_api", parent="candidate supplied diagnostic text",
        )
        diagnostic = cargo_diagnostics(stdout, "check")[0]
        self.assertEqual("rustc-diagnostic", diagnostic["code"])
        partition = partition_cargo_diagnostics(
            gate_kind="cargo-check", diagnostics=[diagnostic],
            candidate_members=[_member("a")],
            rust_project_ir=_ir(modules=[_module("a")]),
        )
        self.assertEqual("diagnostic-unclassified", partition.admission_blocker)

    def test_environment_link_or_cargo_failure_never_enters_intake(self) -> None:
        missing_library = cargo_diagnostics(
            _linker_stdout(child="rust-lld: error: unable to find library -lssl"),
            "check",
        )
        offline = cargo_check_diagnostics("", "check", 101)
        for label, diagnostics in (
            ("missing-native-library", missing_library),
            ("offline-or-tool-failure", offline),
        ):
            with self.subTest(label=label):
                partition = partition_cargo_diagnostics(
                    gate_kind="cargo-check", diagnostics=diagnostics,
                    candidate_members=[_member("a")],
                    rust_project_ir=_ir(modules=[_module("a")]),
                )
                self.assertIsNotNone(partition.admission_blocker)
                self.assertEqual([], partition.project_diagnostics)

    def test_mixed_linker_failure_blocks_the_entire_parent(self) -> None:
        failures = (
            "rust-lld: error: unable to find library -lssl",
            "ld.lld: error: cannot open output file app: Permission denied",
            "collect2: fatal error: cannot find 'ld'",
            "ld: final link failed: No space left on device",
            "rust-lld: error: linker input unavailable in offline mode",
            "link.exe: fatal error LNK1104: cannot open file 'kernel32.lib'",
            "rust-lld: error: undefined symbol: bad/symbol",
        )
        for failure in failures:
            with self.subTest(failure=failure):
                diagnostics = cargo_diagnostics(
                    _linker_stdout(
                        child=(
                            "rust-lld: error: undefined symbol: shared_api\n"
                            ">>> referenced by /private/generated.rs\n"
                            f"{failure}"
                        )
                    ),
                    "check",
                )
                self.assertEqual(1, len(diagnostics))
                self.assertEqual(
                    "linker-diagnostic-unclassified",
                    diagnostics[0]["code"],
                )
                self.assertNotIn("linker_symbol", diagnostics[0])
                partition = partition_cargo_diagnostics(
                    gate_kind="cargo-check", diagnostics=diagnostics,
                    candidate_members=[_member("a")],
                    rust_project_ir=_ir(
                        modules=[_module("a")],
                        public_api=[{
                            "declaration_id": "public-shared",
                            "module_id": "module-a",
                            "symbol": "shared_api",
                        }],
                    ),
                )
                self.assertIsNotNone(partition.admission_blocker)
                self.assertEqual([], partition.project_diagnostics)

    def test_common_linker_context_keeps_strict_symbol_classification(self) -> None:
        cases = (
            (
                "rust-lld: error: undefined symbol: shared_api\n"
                ">>> referenced by /private/generated.rs\n"
                ">>>               generated.o:(entry)"
            ),
            (
                "object.o: in function `entry':\n"
                "object.o: undefined reference to `shared_api'\n"
                "collect2: error: ld returned 1 exit status"
            ),
            (
                "LINK : error LNK2001: unresolved external symbol shared_api\n"
                "app.exe : fatal error LNK1120: 1 unresolved external"
            ),
        )
        for child in cases:
            with self.subTest(child=child):
                diagnostics = cargo_diagnostics(
                    _linker_stdout(child=child), "check",
                )
                self.assertEqual(1, len(diagnostics))
                self.assertEqual(
                    "linker-undefined-symbol", diagnostics[0]["code"],
                )
                self.assertEqual("shared_api", diagnostics[0]["linker_symbol"])

    def test_link_symbol_overflow_blocks_instead_of_truncating(self) -> None:
        diagnostics = cargo_diagnostics(
            _linker_stdout(*(f"symbol_{index}" for index in range(9))), "check",
        )
        self.assertEqual("linker-symbol-overflow", diagnostics[0]["code"])
        self.assertNotIn("origin", diagnostics[0])
        partition = partition_cargo_diagnostics(
            gate_kind="cargo-check", diagnostics=diagnostics,
            candidate_members=[_member("a")],
            rust_project_ir=_ir(modules=[_module("a")]),
        )
        self.assertEqual("diagnostic-not-structured", partition.admission_blocker)

    def test_gnu_and_msvc_messages_use_the_same_strict_symbol_shape(self) -> None:
        cases = (
            (
                "linking with `cc` failed: exit status: 1",
                "object.o: undefined reference to `shared_api'",
            ),
            (
                "linking with `link.exe` failed: exit code: 1120",
                "LINK : error LNK2001: unresolved external symbol shared_api",
            ),
        )
        for parent, child in cases:
            with self.subTest(parent=parent):
                diagnostic = cargo_diagnostics(
                    _linker_stdout(parent=parent, child=child), "check",
                )[0]
                self.assertEqual("linker-undefined-symbol", diagnostic["code"])
                self.assertEqual("shared_api", diagnostic["linker_symbol"])


def _linker_stdout(
    *symbols: str, parent: str = "linking with `cc` failed: exit status: 1",
    child: str | None = None,
) -> str:
    notes = child or "\n".join(
        f"rust-lld: error: undefined symbol: {symbol}\n"
        ">>> referenced by /private/generated.rs"
        for symbol in symbols
    )
    return json.dumps({
        "reason": "compiler-message",
        "message": {
            "level": "error", "code": None, "message": parent,
            "children": [{"level": "note", "message": notes}],
            "spans": [], "rendered": "C:/private/rendered source",
        },
    }) + "\n"


def _member(suffix: str) -> dict:
    return {
        "unit_id": f"unit-{suffix}", "artifact_id": f"candidate-{suffix}",
        "content_sha256": suffix * 64,
    }


def _module(suffix: str) -> dict:
    return {
        "unit_id": f"unit-{suffix}", "candidate_sha256": suffix * 64,
        "rust_path": f"src/unit_{suffix * 64}.rs",
        "module_id": f"module-{suffix}",
    }


def _ir(
    *, modules: list[dict], public_api: list[dict] | None = None,
    ffi_boundaries: list[dict] | None = None,
) -> dict:
    return {
        "modules": modules, "public_api": public_api or [],
        "global_ownership": [], "initialization": [],
        "ffi_boundaries": ffi_boundaries or [],
    }


if __name__ == "__main__":
    unittest.main()
